from datetime import date
import re
import unicodedata

import pandas as pd
import streamlit as st

from auxiliar.google_sheets import (
    append_sheet_data,
    get_or_create_sheet_data,
    get_sheet_data,
)


NOME_ABA_MEDICOS = "lista_medicos"
NOME_ABA_PRESENCA = "base_presenca"


# ============================================================
# Funções auxiliares
# ============================================================

def normalizar_texto(valor: str) -> str:
    """
    Remove acentos e trata underline, hífen e espaços
    como equivalentes.
    """
    texto = str(valor).strip().lower()

    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ascii", "ignore").decode("ascii")

    texto = texto.replace("_", " ")
    texto = texto.replace("-", " ")
    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()


def validar_colunas(
    dataframe: pd.DataFrame,
    nome_aba: str,
    colunas_obrigatorias: list[str],
) -> None:
    """
    Verifica se a planilha possui as colunas necessárias.
    """
    colunas_ausentes = [
        coluna
        for coluna in colunas_obrigatorias
        if coluna not in dataframe.columns
    ]

    if colunas_ausentes:
        raise ValueError(
            f"A aba '{nome_aba}' não possui as colunas: "
            f"{', '.join(colunas_ausentes)}."
        )


def presenca_ja_registrada(
    base_presenca_df: pd.DataFrame,
    data_presenca: date,
    medico: str,
) -> bool:
    """
    Verifica se já existe presença registrada para o
    médico na data informada.
    """
    if base_presenca_df.empty:
        return False

    datas = pd.to_datetime(
        base_presenca_df["data"]
        .fillna("")
        .astype(str)
        .str.strip(),
        format="%d/%m/%Y",
        errors="coerce",
    )

    medicos = (
        base_presenca_df["medico"]
        .fillna("")
        .apply(normalizar_texto)
    )

    return bool(
        (
            datas.eq(pd.Timestamp(data_presenca))
            & medicos.eq(normalizar_texto(medico))
        ).any()
    )


# ============================================================
# Estado da página
# ============================================================

if "versao_formulario_presenca" not in st.session_state:
    st.session_state["versao_formulario_presenca"] = 0


mensagem_sucesso = st.session_state.pop(
    "mensagem_sucesso_presenca",
    None,
)

if mensagem_sucesso:
    st.success(mensagem_sucesso)


versao_formulario = st.session_state[
    "versao_formulario_presenca"
]


# ============================================================
# Cabeçalho
# ============================================================

with st.container(border=True):
    coluna_icone, coluna_titulo = st.columns(
        [1, 8],
        vertical_alignment="center",
    )

    with coluna_icone:
        st.markdown("# 🙋")

    with coluna_titulo:
        st.title("Registrar presença sem exame")

        st.caption(
            "ARLONSP - SERVIÇOS MÉDICOS | "
            "Dias em que o médico veio, mas não realizou exames"
        )


st.info(
    "Use esta página quando o médico compareceu, mas não "
    "realizou nenhum exame. Nesses dias ele recebe o valor "
    "mínimo diário (metade, se o dia for marcado como meio "
    "período). Se depois forem lançados exames na mesma data, "
    "os exames passam a valer normalmente."
)


# ============================================================
# Carregamento das planilhas
# ============================================================

try:
    with st.spinner("Carregando médicos..."):
        lista_medicos_df = get_sheet_data(
            NOME_ABA_MEDICOS
        ).copy()

        base_presenca_df = get_or_create_sheet_data(
            NOME_ABA_PRESENCA,
            [
                "data",
                "medico",
            ],
        ).copy()

except Exception as error:
    st.error(
        "Não foi possível carregar os dados das planilhas."
    )
    st.exception(error)
    st.stop()


lista_medicos_df.columns = (
    lista_medicos_df.columns
    .astype(str)
    .str.strip()
)

base_presenca_df.columns = (
    base_presenca_df.columns
    .astype(str)
    .str.strip()
)


try:
    validar_colunas(
        lista_medicos_df,
        NOME_ABA_MEDICOS,
        ["nome_medico"],
    )

    validar_colunas(
        base_presenca_df,
        NOME_ABA_PRESENCA,
        [
            "data",
            "medico",
        ],
    )

except ValueError as error:
    st.error(str(error))
    st.stop()


nomes_medicos = (
    lista_medicos_df["nome_medico"]
    .dropna()
    .astype(str)
    .str.strip()
)

nomes_medicos = (
    nomes_medicos.loc[nomes_medicos.ne("")]
    .drop_duplicates()
    .sort_values()
    .tolist()
)


if not nomes_medicos:
    st.warning(
        "Nenhum médico foi encontrado na aba "
        "`lista_medicos`."
    )
    st.stop()


# ============================================================
# Formulário
# ============================================================

with st.container(border=True):
    st.markdown("### Dados da presença")

    with st.form(
        key=f"formulario_presenca_{versao_formulario}"
    ):
        coluna_data, coluna_medico = st.columns(
            [1, 2]
        )

        with coluna_data:
            data_presenca = st.date_input(
                "Data",
                value=date.today(),
                format="DD/MM/YYYY",
            )

        with coluna_medico:
            medico_selecionado = st.selectbox(
                "Médico",
                options=nomes_medicos,
                index=None,
                placeholder="Selecione um médico",
            )

        salvar_presenca = st.form_submit_button(
            "💾 Salvar presença",
            type="primary",
            use_container_width=True,
        )


# ============================================================
# Salvamento
# ============================================================

if salvar_presenca:
    if not medico_selecionado:
        st.warning(
            "Selecione um médico antes de salvar."
        )

    elif presenca_ja_registrada(
        base_presenca_df,
        data_presenca,
        medico_selecionado,
    ):
        st.warning(
            f"Já existe presença registrada para "
            f"{medico_selecionado} em "
            f"{data_presenca.strftime('%d/%m/%Y')}."
        )

    else:
        # Ordem das colunas em base_presenca:
        #
        # data
        # medico

        nova_linha = [
            data_presenca.strftime("%d/%m/%Y"),
            medico_selecionado,
        ]

        try:
            with st.spinner("Salvando presença..."):
                append_sheet_data(
                    NOME_ABA_PRESENCA,
                    [nova_linha],
                )

            st.session_state[
                "mensagem_sucesso_presenca"
            ] = (
                f"Presença sem exame de {medico_selecionado} "
                f"em {data_presenca.strftime('%d/%m/%Y')} "
                "salva com sucesso."
            )

            st.session_state[
                "versao_formulario_presenca"
            ] += 1

            st.rerun()

        except Exception as error:
            st.error(
                "Não foi possível salvar a presença "
                "na planilha."
            )
            st.exception(error)


st.caption(
    "Para corrigir ou excluir registros, use Configurações → "
    "Presença sem exame."
)
