from datetime import date
import re
import unicodedata

import pandas as pd
import streamlit as st

from auxiliar.google_sheets import (
    append_sheet_data,
    get_sheet_data,
)


NOME_ABA_MEDICOS = "lista_medicos"
NOME_ABA_OUTROS_VALORES = "outros_valores"
NOME_ABA_SOBREAVISO = "base_sobreaviso"


# ============================================================
# Funções auxiliares
# ============================================================

def formatar_moeda(valor: float) -> str:
    """
    Formata um número como moeda brasileira.
    """
    valor_formatado = f"{float(valor):,.2f}"

    valor_formatado = (
        valor_formatado
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )

    return f"R$ {valor_formatado}"


def converter_para_float(valor) -> float:
    """
    Converte valores como:
        100
        100.50
        "100,50"
        "R$ 1.200,50"

    para float.
    """
    if valor is None or pd.isna(valor):
        return 0.0

    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip()

    if not texto:
        return 0.0

    texto = re.sub(r"[R$\s]", "", texto)

    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            # Formato brasileiro: 1.234,56
            texto = texto.replace(".", "")
            texto = texto.replace(",", ".")
        else:
            # Formato internacional: 1,234.56
            texto = texto.replace(",", "")

    elif "," in texto:
        texto = texto.replace(".", "")
        texto = texto.replace(",", ".")

    try:
        return float(texto)

    except ValueError as error:
        raise ValueError(
            f"Não foi possível converter o valor '{valor}' "
            "para número."
        ) from error


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


def obter_valor_sobreaviso(
    outros_valores_df: pd.DataFrame,
) -> float:
    """
    Busca valor_sobreaviso na coluna descricao
    da aba outros_valores.
    """
    base = outros_valores_df.copy()

    base["descricao_normalizada"] = (
        base["descricao"]
        .fillna("")
        .apply(normalizar_texto)
    )

    resultado = base.loc[
        base["descricao_normalizada"].eq("valor sobreaviso")
    ]

    if resultado.empty:
        raise ValueError(
            "A descrição 'valor_sobreaviso' não foi encontrada "
            "na aba 'outros_valores'."
        )

    # Caso existam registros duplicados, utiliza o último.
    valor = resultado.iloc[-1]["valor"]

    return converter_para_float(valor)


# ============================================================
# Estado da página
# ============================================================

if "versao_formulario_sobreaviso" not in st.session_state:
    st.session_state["versao_formulario_sobreaviso"] = 0


mensagem_sucesso = st.session_state.pop(
    "mensagem_sucesso_sobreaviso",
    None,
)

if mensagem_sucesso:
    st.success(mensagem_sucesso)


versao_formulario = st.session_state[
    "versao_formulario_sobreaviso"
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
        st.markdown("# 🚨")

    with coluna_titulo:
        st.title("Inserir sobreaviso")

        st.caption(
            "ARLONSP - SERVIÇOS MÉDICOS | "
            "Registro de sobreaviso médico"
        )


# ============================================================
# Carregamento das planilhas
# ============================================================

try:
    with st.spinner("Carregando médicos e valores..."):
        lista_medicos_df = get_sheet_data(
            NOME_ABA_MEDICOS
        ).copy()

        outros_valores_df = get_sheet_data(
            NOME_ABA_OUTROS_VALORES
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

outros_valores_df.columns = (
    outros_valores_df.columns
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
        outros_valores_df,
        NOME_ABA_OUTROS_VALORES,
        [
            "descricao",
            "valor",
        ],
    )

    valor_sobreaviso_12h = obter_valor_sobreaviso(
        outros_valores_df
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
# Valor base do sobreaviso
# ============================================================

with st.container(border=True):
    coluna_texto, coluna_valor = st.columns(
        [3, 1],
        vertical_alignment="center",
    )

    with coluna_texto:
        st.markdown("### Valor do sobreaviso 12h")

        st.caption(
            "Valor definido em Configurações → Outros valores."
        )

    with coluna_valor:
        st.metric(
            "Valor",
            formatar_moeda(valor_sobreaviso_12h),
        )


# ============================================================
# Formulário
# ============================================================

with st.container(border=True):
    st.markdown("### Dados do sobreaviso")

    with st.form(
        key=f"formulario_sobreaviso_{versao_formulario}"
    ):
        coluna_data, coluna_medico, coluna_periodo = st.columns(
            [1, 2, 1]
        )

        with coluna_data:
            data_sobreaviso = st.date_input(
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

        with coluna_periodo:
            tipo_sobreaviso = st.selectbox(
                "Período",
                options=[
                    "12h",
                    "24h",
                ],
                index=0,
            )

        salvar_sobreaviso = st.form_submit_button(
            "💾 Salvar sobreaviso",
            type="primary",
            use_container_width=True,
        )


# ============================================================
# Salvamento
# ============================================================

if salvar_sobreaviso:
    if not medico_selecionado:
        st.warning(
            "Selecione um médico antes de salvar."
        )

    else:
        multiplicador_sobreaviso = (
            2
            if tipo_sobreaviso == "24h"
            else 1
        )

        valor_sobreaviso_final = (
            valor_sobreaviso_12h
            * multiplicador_sobreaviso
        )

        # Ordem das colunas em base_sobreaviso:
        #
        # data
        # medico
        # valor

        nova_linha = [
            data_sobreaviso.strftime("%d/%m/%Y"),
            medico_selecionado,
            valor_sobreaviso_final,
        ]

        try:
            with st.spinner("Salvando sobreaviso..."):
                append_sheet_data(
                    NOME_ABA_SOBREAVISO,
                    [nova_linha],
                )

            st.session_state[
                "mensagem_sucesso_sobreaviso"
            ] = (
                f"Sobreaviso de {tipo_sobreaviso} de "
                f"{medico_selecionado}, no valor de "
                f"{formatar_moeda(valor_sobreaviso_final)}, "
                "salvo com sucesso."
            )

            st.session_state[
                "versao_formulario_sobreaviso"
            ] += 1

            st.rerun()

        except Exception as error:
            st.error(
                "Não foi possível salvar o sobreaviso "
                "na planilha."
            )
            st.exception(error)