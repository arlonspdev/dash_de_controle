from calendar import monthrange
from datetime import date
import re

import pandas as pd
import streamlit as st

from auxiliar.google_sheets import get_sheet_data


NOME_ABA_BASE_DADOS = "base_dados"
NOME_ABA_MEDICOS = "lista_medicos"
TODOS_OS_MEDICOS = "Todos os médicos"


# ============================================================
# Funções auxiliares
# ============================================================

def formatar_moeda(valor: float) -> str:
    """
    Formata um número como moeda brasileira.

    Exemplo:
        1234.5 -> R$ 1.234,50
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
    Converte valores numéricos ou monetários para float.

    Exemplos aceitos:
        100
        100.50
        "100,50"
        "R$ 1.200,50"
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

    return float(texto)


def converter_coluna_monetaria(
    serie: pd.Series,
    nome_coluna: str,
) -> pd.Series:
    """
    Converte uma coluna inteira para float.

    Caso algum valor não possa ser convertido, mostra quais
    linhas da planilha precisam ser corrigidas.
    """
    valores_convertidos = []
    linhas_invalidas = []

    for indice, valor in serie.items():
        try:
            valores_convertidos.append(
                converter_para_float(valor)
            )

        except (TypeError, ValueError):
            valores_convertidos.append(0.0)

            # +2 considera o cabeçalho e o índice iniciado em zero.
            linhas_invalidas.append(indice + 2)

    if linhas_invalidas:
        linhas_texto = ", ".join(
            str(linha)
            for linha in linhas_invalidas[:10]
        )

        raise ValueError(
            f"A coluna '{nome_coluna}' possui valores inválidos "
            f"nas linhas: {linhas_texto}."
        )

    return pd.Series(
        valores_convertidos,
        index=serie.index,
        dtype=float,
    )


def converter_coluna_data(serie: pd.Series) -> pd.Series:
    """
    Converte datas nos formatos:

        DD/MM/AAAA
        AAAA-MM-DD

    Também tenta reconhecer outros formatos com dia primeiro.
    """
    texto = (
        serie
        .fillna("")
        .astype(str)
        .str.strip()
    )

    datas = pd.to_datetime(
        texto,
        format="%d/%m/%Y",
        errors="coerce",
    )

    mascara_invalida = datas.isna()

    datas.loc[mascara_invalida] = pd.to_datetime(
        texto.loc[mascara_invalida],
        format="%Y-%m-%d",
        errors="coerce",
    )

    mascara_invalida = datas.isna()

    datas.loc[mascara_invalida] = pd.to_datetime(
        texto.loc[mascara_invalida],
        dayfirst=True,
        errors="coerce",
    )

    return datas.dt.normalize()


def validar_colunas(
    dataframe: pd.DataFrame,
    nome_aba: str,
    colunas_obrigatorias: list[str],
) -> None:
    """
    Confere se a planilha possui todas as colunas necessárias.
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


def exibir_cards(
    total_exames: float,
    total_taxa_aparelho: float,
    total_medico: float,
    total_final_medico: float,
) -> None:
    """
    Exibe os totais financeiros do período.
    """
    st.markdown("### Totais do período")

    coluna_1, coluna_2, coluna_3, coluna_4 = st.columns(4)

    with coluna_1:
        st.metric(
            "Total dos exames",
            formatar_moeda(total_exames),
        )

    with coluna_2:
        st.metric(
            "Total taxa aparelho",
            formatar_moeda(total_taxa_aparelho),
        )

    with coluna_3:
        st.metric(
            "Total médico",
            formatar_moeda(total_medico),
            help="Total antes da aplicação do valor mínimo.",
        )

    with coluna_4:
        st.metric(
            "Total final médico",
            formatar_moeda(total_final_medico),
            help="Total após a aplicação do valor mínimo diário.",
        )


# ============================================================
# Cabeçalho
# ============================================================

with st.container(border=True):
    coluna_icone, coluna_titulo = st.columns(
        [1, 8],
        vertical_alignment="center",
    )

    with coluna_icone:
        st.markdown("# 💰")

    with coluna_titulo:
        st.title("Controle financeiro")

        st.caption(
            "ARLONSP - SERVIÇOS MÉDICOS | "
            "Resumo financeiro dos atendimentos"
        )


# ============================================================
# Carregamento dos dados
# ============================================================

try:
    with st.spinner("Carregando dados financeiros..."):
        base_dados_df = get_sheet_data(
            NOME_ABA_BASE_DADOS
        ).copy()

        lista_medicos_df = get_sheet_data(
            NOME_ABA_MEDICOS
        ).copy()

except Exception as error:
    st.error(
        "Não foi possível carregar os dados das planilhas."
    )
    st.exception(error)
    st.stop()


base_dados_df.columns = (
    base_dados_df.columns
    .astype(str)
    .str.strip()
)

lista_medicos_df.columns = (
    lista_medicos_df.columns
    .astype(str)
    .str.strip()
)


try:
    validar_colunas(
        base_dados_df,
        NOME_ABA_BASE_DADOS,
        [
            "data",
            "nome_medico",
            "valor_exame",
            "taxa_aparelho",
            "valor_medico",
        ],
    )

    validar_colunas(
        lista_medicos_df,
        NOME_ABA_MEDICOS,
        [
            "nome_medico",
            "valor_minimo",
        ],
    )

except ValueError as error:
    st.error(str(error))
    st.stop()


# ============================================================
# Tratamento da base de médicos
# ============================================================

lista_medicos_df["nome_medico"] = (
    lista_medicos_df["nome_medico"]
    .fillna("")
    .astype(str)
    .str.strip()
)

lista_medicos_df = lista_medicos_df.loc[
    lista_medicos_df["nome_medico"].ne("")
].copy()


try:
    lista_medicos_df["valor_minimo"] = (
        converter_coluna_monetaria(
            lista_medicos_df["valor_minimo"],
            "valor_minimo",
        )
    )

except ValueError as error:
    st.error(str(error))
    st.stop()


medicos_duplicados = (
    lista_medicos_df.loc[
        lista_medicos_df["nome_medico"].duplicated(
            keep=False
        ),
        "nome_medico",
    ]
    .drop_duplicates()
    .tolist()
)


if medicos_duplicados:
    st.warning(
        "Existem médicos duplicados na aba `lista_medicos`. "
        "Será utilizado o último valor mínimo cadastrado para: "
        + ", ".join(medicos_duplicados)
    )


lista_medicos_df = (
    lista_medicos_df
    .drop_duplicates(
        subset=["nome_medico"],
        keep="last",
    )
    [["nome_medico", "valor_minimo"]]
)


# ============================================================
# Tratamento da base de atendimentos
# ============================================================

base_dados_df["nome_medico"] = (
    base_dados_df["nome_medico"]
    .fillna("")
    .astype(str)
    .str.strip()
)

base_dados_df["data_convertida"] = converter_coluna_data(
    base_dados_df["data"]
)


quantidade_datas_invalidas = int(
    base_dados_df["data_convertida"].isna().sum()
)


if quantidade_datas_invalidas:
    st.warning(
        f"{quantidade_datas_invalidas} registro(s) possuem uma "
        "data inválida e não serão considerados nos cálculos."
    )


base_dados_df = base_dados_df.loc[
    base_dados_df["data_convertida"].notna()
    & base_dados_df["nome_medico"].ne("")
].copy()


try:
    for coluna_monetaria in [
        "valor_exame",
        "taxa_aparelho",
        "valor_medico",
    ]:
        base_dados_df[coluna_monetaria] = (
            converter_coluna_monetaria(
                base_dados_df[coluna_monetaria],
                coluna_monetaria,
            )
        )

except ValueError as error:
    st.error(str(error))
    st.stop()


# ============================================================
# Período padrão: mês atual
# ============================================================

hoje = date.today()

primeiro_dia_mes = hoje.replace(day=1)

ultimo_dia_mes = hoje.replace(
    day=monthrange(
        hoje.year,
        hoje.month,
    )[1]
)


# ============================================================
# Filtros
# ============================================================

medicos_cadastrados = (
    lista_medicos_df["nome_medico"]
    .dropna()
    .astype(str)
    .str.strip()
    .tolist()
)

medicos_com_atendimento = (
    base_dados_df["nome_medico"]
    .dropna()
    .astype(str)
    .str.strip()
    .tolist()
)

opcoes_medicos = sorted(
    set(medicos_cadastrados)
    | set(medicos_com_atendimento)
)


with st.container(border=True):
    st.markdown("### Filtros")

    coluna_periodo, coluna_medico = st.columns(
        [2, 1]
    )

    with coluna_periodo:
        periodo_selecionado = st.date_input(
            "Período",
            value=(
                primeiro_dia_mes,
                ultimo_dia_mes,
            ),
            format="DD/MM/YYYY",
        )

    with coluna_medico:
        medico_selecionado = st.selectbox(
            "Médico",
            options=[
                TODOS_OS_MEDICOS,
                *opcoes_medicos,
            ],
            index=0,
        )


if (
    not isinstance(
        periodo_selecionado,
        (tuple, list),
    )
    or len(periodo_selecionado) != 2
):
    st.info(
        "Selecione a data inicial e a data final do período."
    )
    st.stop()


data_inicial, data_final = periodo_selecionado


if data_inicial > data_final:
    data_inicial, data_final = (
        data_final,
        data_inicial,
    )


data_inicial_timestamp = pd.Timestamp(data_inicial)
data_final_timestamp = pd.Timestamp(data_final)


# ============================================================
# Aplicação dos filtros
# ============================================================

base_filtrada_df = base_dados_df.loc[
    base_dados_df["data_convertida"].between(
        data_inicial_timestamp,
        data_final_timestamp,
        inclusive="both",
    )
].copy()


if medico_selecionado != TODOS_OS_MEDICOS:
    base_filtrada_df = base_filtrada_df.loc[
        base_filtrada_df["nome_medico"].eq(
            medico_selecionado
        )
    ].copy()


# ============================================================
# Agrupamento por dia e médico
# ============================================================

if base_filtrada_df.empty:
    exibir_cards(
        total_exames=0,
        total_taxa_aparelho=0,
        total_medico=0,
        total_final_medico=0,
    )

    st.info(
        "Nenhum atendimento foi encontrado para os filtros "
        "selecionados."
    )

    st.stop()


resumo_financeiro_df = (
    base_filtrada_df
    .groupby(
        [
            "data_convertida",
            "nome_medico",
        ],
        as_index=False,
    )
    .agg(
        valor_exame=("valor_exame", "sum"),
        taxa_aparelho=("taxa_aparelho", "sum"),
        valor_medico=("valor_medico", "sum"),
    )
)


# ============================================================
# Inclusão do valor mínimo do médico
# ============================================================

resumo_financeiro_df = resumo_financeiro_df.merge(
    lista_medicos_df,
    how="left",
    on="nome_medico",
)


medicos_sem_valor_minimo = (
    resumo_financeiro_df.loc[
        resumo_financeiro_df["valor_minimo"].isna(),
        "nome_medico",
    ]
    .drop_duplicates()
    .tolist()
)


if medicos_sem_valor_minimo:
    st.warning(
        "Os seguintes médicos não possuem valor mínimo "
        "cadastrado e utilizarão R$ 0,00: "
        + ", ".join(medicos_sem_valor_minimo)
    )


resumo_financeiro_df["valor_minimo"] = (
    resumo_financeiro_df["valor_minimo"]
    .fillna(0.0)
    .astype(float)
)


resumo_financeiro_df["pagar_valor_minimo"] = (
    resumo_financeiro_df["valor_medico"]
    < resumo_financeiro_df["valor_minimo"]
)


resumo_financeiro_df["valor_final_medico"] = (
    resumo_financeiro_df[
        [
            "valor_medico",
            "valor_minimo",
        ]
    ]
    .max(axis=1)
)


resumo_financeiro_df = (
    resumo_financeiro_df
    .sort_values(
        [
            "data_convertida",
            "nome_medico",
        ]
    )
    .reset_index(drop=True)
)


# ============================================================
# Cards
# ============================================================

total_exames = resumo_financeiro_df[
    "valor_exame"
].sum()

total_taxa_aparelho = resumo_financeiro_df[
    "taxa_aparelho"
].sum()

total_medico = resumo_financeiro_df[
    "valor_medico"
].sum()

total_final_medico = resumo_financeiro_df[
    "valor_final_medico"
].sum()


exibir_cards(
    total_exames=total_exames,
    total_taxa_aparelho=total_taxa_aparelho,
    total_medico=total_medico,
    total_final_medico=total_final_medico,
)


# ============================================================
# Tabela para exibição
# ============================================================

tabela_exibicao_df = resumo_financeiro_df[
    [
        "data_convertida",
        "nome_medico",
        "valor_exame",
        "taxa_aparelho",
        "valor_medico",
        "pagar_valor_minimo",
        "valor_final_medico",
    ]
].copy()


tabela_exibicao_df = tabela_exibicao_df.rename(
    columns={
        "data_convertida": "Data",
        "nome_medico": "Médico",
        "valor_exame": "Valor dos exames",
        "taxa_aparelho": "Taxa do aparelho",
        "valor_medico": "Valor médico",
        "pagar_valor_minimo": "Pagar valor mínimo",
        "valor_final_medico": "Valor final médico",
    }
)


tabela_exibicao_df["Data"] = (
    tabela_exibicao_df["Data"].dt.date
)


st.markdown("### Detalhamento diário por médico")

st.caption(
    f"Período de {data_inicial.strftime('%d/%m/%Y')} "
    f"até {data_final.strftime('%d/%m/%Y')}."
)


st.dataframe(
    tabela_exibicao_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Data": st.column_config.DateColumn(
            "Data",
            format="DD/MM/YYYY",
        ),
        "Médico": st.column_config.TextColumn(
            "Médico",
            width="medium",
        ),
        "Valor dos exames": st.column_config.NumberColumn(
            "Valor dos exames",
            format="R$ %.2f",
        ),
        "Taxa do aparelho": st.column_config.NumberColumn(
            "Taxa do aparelho",
            format="R$ %.2f",
        ),
        "Valor médico": st.column_config.NumberColumn(
            "Valor médico",
            format="R$ %.2f",
            help="Valor calculado antes da aplicação do mínimo.",
        ),
        "Pagar valor mínimo": (
            st.column_config.CheckboxColumn(
                "Pagar valor mínimo",
                help=(
                    "Marcado quando o valor diário do médico "
                    "é menor que seu valor mínimo."
                ),
            )
        ),
        "Valor final médico": (
            st.column_config.NumberColumn(
                "Valor final médico",
                format="R$ %.2f",
                help=(
                    "Maior valor entre o total diário do médico "
                    "e o valor mínimo cadastrado."
                ),
            )
        ),
    },
)