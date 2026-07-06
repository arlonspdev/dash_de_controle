from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import gspread
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe


# Loads values from .env when running locally.
# On Streamlit Cloud, values will come from st.secrets.
load_dotenv()


GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _get_setting(
    setting_name: str,
    default: Any = None,
) -> Any:
    """
    Retrieve a setting from Streamlit Secrets.

    If it is not available there, try an environment variable.
    This allows the same code to work on Streamlit Cloud and locally.
    """
    try:
        if setting_name in st.secrets:
            return st.secrets[setting_name]
    except FileNotFoundError:
        # No local .streamlit/secrets.toml file was found.
        pass

    return os.environ.get(setting_name, default)


def _get_credentials_info() -> dict:
    """
    Load the Google service-account credentials.

    GOOGLE_CREDENTIALS_JSON may be:
    1. A JSON string.
    2. A path to a JSON file.
    3. A TOML section converted into a dictionary.
    """
    credential_input = _get_setting("GOOGLE_CREDENTIALS_JSON")

    if not credential_input:
        raise RuntimeError(
            "The GOOGLE_CREDENTIALS_JSON secret was not configured."
        )

    # Supports credentials configured as a TOML dictionary.
    if isinstance(credential_input, Mapping):
        return dict(credential_input)

    credential_text = str(credential_input).strip()

    # Supports a local path to a service-account JSON file.
    possible_path = Path(credential_text).expanduser()

    if possible_path.is_file():
        with possible_path.open(
            mode="r",
            encoding="utf-8",
        ) as credential_file:
            return json.load(credential_file)

    # Supports the complete JSON stored as text in secrets.toml or .env.
    try:
        return json.loads(credential_text)

    except json.JSONDecodeError as error:
        raise RuntimeError(
            "GOOGLE_CREDENTIALS_JSON is not valid JSON and is not "
            "a valid path to a JSON file."
        ) from error


def get_credentials() -> Credentials:
    """
    Create Google credentials from the configured service account.
    """
    credentials_info = _get_credentials_info()

    return Credentials.from_service_account_info(
        credentials_info,
        scopes=GOOGLE_SCOPES,
    )


@st.cache_resource
def create_client() -> gspread.Client:
    """
    Create and cache the authenticated gspread client.
    """
    credentials = get_credentials()
    return gspread.authorize(credentials)


def _get_spreadsheet_id(
    spreadsheet_id: str | None = None,
) -> str:
    """
    Return a supplied spreadsheet ID or the default ID from secrets.
    """
    resolved_id = spreadsheet_id or _get_setting("SPREADSHEET_ID")

    if not resolved_id:
        raise RuntimeError(
            "The SPREADSHEET_ID secret was not configured."
        )

    return str(resolved_id)


@st.cache_resource
def _open_spreadsheet(
    spreadsheet_id: str,
) -> gspread.Spreadsheet:
    """
    Open and cache a spreadsheet connection.
    """
    client = create_client()
    return client.open_by_key(spreadsheet_id)


def get_spreadsheet(
    spreadsheet_id: str | None = None,
) -> gspread.Spreadsheet:
    """
    Return the requested spreadsheet.

    When spreadsheet_id is omitted, SPREADSHEET_ID_2 is used.
    """
    resolved_id = _get_spreadsheet_id(spreadsheet_id)
    return _open_spreadsheet(resolved_id)


@st.cache_data(
    ttl=300,
    show_spinner=False,
)
def get_sheet_data(
    sheet_name: str,
    sheet_id: str | None = None,
) -> pd.DataFrame:
    """
    Read a Google Sheets worksheet and return it as a DataFrame.

    The first row of the worksheet is treated as the column header.
    """
    spreadsheet = get_spreadsheet(sheet_id)
    worksheet = spreadsheet.worksheet(sheet_name)

    values = worksheet.get_all_values()

    if not values:
        return pd.DataFrame()

    header = values[0]
    rows = values[1:]

    return pd.DataFrame(
        rows,
        columns=header,
    )


def set_sheet_data(
    sheet_name: str,
    dataframe: pd.DataFrame,
    sheet_id: str | None = None,
) -> None:
    """
    Clear a worksheet and replace its content with a DataFrame.
    """
    spreadsheet = get_spreadsheet(sheet_id)
    worksheet = spreadsheet.worksheet(sheet_name)

    worksheet.clear()

    set_with_dataframe(
        worksheet,
        dataframe,
        include_index=False,
        include_column_header=True,
        resize=True,
    )

    # Prevent the app from showing previously cached data.
    get_sheet_data.clear()


def append_sheet_data(
    sheet_name: str,
    data: list[list[Any]],
    sheet_id: str | None = None,
) -> None:
    """
    Append multiple rows to a worksheet.
    """
    if not data:
        return

    spreadsheet = get_spreadsheet(sheet_id)
    worksheet = spreadsheet.worksheet(sheet_name)

    worksheet.append_rows(
        data,
        value_input_option="USER_ENTERED",
    )

    # Prevent the app from showing previously cached data.
    get_sheet_data.clear()