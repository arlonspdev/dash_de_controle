from calendar import monthrange
from datetime import date
import re

import pandas as pd
import streamlit as st

from auxiliar.google_sheets import get_sheet_data


NOME_ABA_BASE_DADOS = "base_dados"
NOME_ABA_MEDICOS = "lista_medicos"


# ============================================================
# Funções auxiliares
# ============================================================

def formatar_moeda(valor: float) -> str:
    """
    Formata um valor como moeda brasileira.

    Exemplo:
        1234.50 -> R$ 1.234,50
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
    Converte valores monetários para float.

    Aceita, por exemplo:
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

            # Soma 2 para considerar o cabeçalho da planilha
            # e o índice iniciado em zero.
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
    Converte as datas da planilha para datetime.
    """
    texto = (
        serie
        .fillna("")
        .astype(str)
        .str.strip()
    )

    # Formato usado ao salvar pelo formulário.
    datas = pd.to_datetime(
        texto,
        format="%d/%m/%Y",
        errors="coerce",
    )

    # Tenta o formato ISO.
    mascara_invalida = datas.isna()

    datas.loc[mascara_invalida] = pd.to_datetime(
        texto.loc[mascara_invalida],
        format="%Y-%m-%d",
        errors="coerce",
    )

    # Última tentativa para formatos diferentes.
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
    Verifica se a planilha possui todas as colunas necessárias.
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
        st.title("Controle financeiro por médico")

        st.caption(
            "ARLONSP - SERVIÇOS MÉDICOS | "
            "Consulta individual dos atendimentos"
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


# Remove espaços acidentais nos nomes das colunas.
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
            "numero_atendimento",
            "nome_paciente",
            "nome_medico",
            "nome_exame",
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
# Tratamento da lista de médicos
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
    .reset_index(drop=True)
)


nomes_medicos = (
    lista_medicos_df["nome_medico"]
    .dropna()
    .astype(str)
    .str.strip()
    .tolist()
)


if not nomes_medicos:
    st.warning(
        "Nenhum médico foi encontrado na aba `lista_medicos`."
    )
    st.stop()


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
        "data inválida e não serão considerados."
    )


base_dados_df = base_dados_df.loc[
    base_dados_df["data_convertida"].notna()
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
            options=nomes_medicos,
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
# Valor mínimo do médico selecionado
# ============================================================

registro_medico = lista_medicos_df.loc[
    lista_medicos_df["nome_medico"].eq(
        medico_selecionado
    )
]


if registro_medico.empty:
    valor_minimo_medico = 0.0

    st.warning(
        "O médico selecionado não possui valor mínimo "
        "cadastrado."
    )

else:
    valor_minimo_medico = float(
        registro_medico.iloc[0]["valor_minimo"]
    )


# ============================================================
# Aplicação dos filtros
# ============================================================

base_filtrada_df = base_dados_df.loc[
    base_dados_df["data_convertida"].between(
        data_inicial_timestamp,
        data_final_timestamp,
        inclusive="both",
    )
    & base_dados_df["nome_medico"].eq(
        medico_selecionado
    )
].copy()


# ============================================================
# Cálculo dos cards
# ============================================================

total_valor_exame = base_filtrada_df[
    "valor_exame"
].sum()

total_taxa_aparelho = base_filtrada_df[
    "taxa_aparelho"
].sum()

total_valor_medico = base_filtrada_df[
    "valor_medico"
].sum()


# O valor mínimo continua sendo analisado por dia.
#
# Exemplo:
# Dia 01: valor médico = R$ 300 e mínimo = R$ 500
#         valor final = R$ 500
#
# Dia 02: valor médico = R$ 700 e mínimo = R$ 500
#         valor final = R$ 700

if base_filtrada_df.empty:
    resumo_diario_df = pd.DataFrame(
        columns=[
            "data_convertida",
            "valor_medico",
            "pagar_valor_minimo",
            "valor_final_medico",
        ]
    )

    total_final_medico = 0.0
    quantidade_dias_valor_minimo = 0

else:
    resumo_diario_df = (
        base_filtrada_df
        .groupby(
            "data_convertida",
            as_index=False,
        )
        .agg(
            valor_medico=("valor_medico", "sum")
        )
    )

    resumo_diario_df["pagar_valor_minimo"] = (
        resumo_diario_df["valor_medico"]
        < valor_minimo_medico
    )

    resumo_diario_df["valor_final_medico"] = (
        resumo_diario_df["valor_medico"]
        .clip(lower=valor_minimo_medico)
    )

    total_final_medico = resumo_diario_df[
        "valor_final_medico"
    ].sum()

    quantidade_dias_valor_minimo = int(
        resumo_diario_df["pagar_valor_minimo"].sum()
    )


# ============================================================
# Cards
# ============================================================

st.markdown("### Totais do período")

coluna_1, coluna_2, coluna_3, coluna_4 = st.columns(4)


with coluna_1:
    st.metric(
        "Valor dos exames",
        formatar_moeda(total_valor_exame),
    )


with coluna_2:
    st.metric(
        "Taxa do aparelho",
        formatar_moeda(total_taxa_aparelho),
    )


with coluna_3:
    st.metric(
        "Valor médico",
        formatar_moeda(total_valor_medico),
        help=(
            "Soma dos valores dos atendimentos antes da "
            "aplicação do valor mínimo diário."
        ),
    )


with coluna_4:
    st.metric(
        "Valor final médico",
        formatar_moeda(total_final_medico),
        delta=(
            formatar_moeda(
                total_final_medico - total_valor_medico
            )
            if total_final_medico > total_valor_medico
            else None
        ),
        help=(
            "Total após aplicar o valor mínimo do médico "
            "em cada dia de atendimento."
        ),
    )


if quantidade_dias_valor_minimo:
    st.info(
        f"O valor mínimo de "
        f"{formatar_moeda(valor_minimo_medico)} foi aplicado em "
        f"{quantidade_dias_valor_minimo} dia(s) do período."
    )

else:
    st.caption(
        f"Valor mínimo diário cadastrado para "
        f"{medico_selecionado}: "
        f"{formatar_moeda(valor_minimo_medico)}."
    )


# ============================================================
# Tabela sem agrupamento
# ============================================================

st.markdown("### Atendimentos")

st.caption(
    f"Atendimentos de {medico_selecionado} entre "
    f"{data_inicial.strftime('%d/%m/%Y')} e "
    f"{data_final.strftime('%d/%m/%Y')}."
)


if base_filtrada_df.empty:
    st.info(
        "Nenhum atendimento foi encontrado para o médico "
        "e período selecionados."
    )

else:
    tabela_exibicao_df = base_filtrada_df[
        [
            "data_convertida",
            "numero_atendimento",
            "nome_paciente",
            "nome_exame",
            "valor_exame",
            "taxa_aparelho",
            "valor_medico",
        ]
    ].copy()

    tabela_exibicao_df = tabela_exibicao_df.sort_values(
        [
            "data_convertida",
            "numero_atendimento",
        ],
        ascending=[
            True,
            True,
        ],
    )

    tabela_exibicao_df = tabela_exibicao_df.rename(
        columns={
            "data_convertida": "Data",
            "numero_atendimento": "Número do atendimento",
            "nome_paciente": "Paciente",
            "nome_exame": "Exame",
            "valor_exame": "Valor do exame",
            "taxa_aparelho": "Taxa do aparelho",
            "valor_medico": "Valor médico",
        }
    )

    tabela_exibicao_df["Data"] = (
        tabela_exibicao_df["Data"].dt.date
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
            "Número do atendimento": (
                st.column_config.TextColumn(
                    "Número do atendimento",
                    width="medium",
                )
            ),
            "Paciente": st.column_config.TextColumn(
                "Paciente",
                width="large",
            ),
            "Exame": st.column_config.TextColumn(
                "Exame",
                width="large",
            ),
            "Valor do exame": (
                st.column_config.NumberColumn(
                    "Valor do exame",
                    format="R$ %.2f",
                )
            ),
            "Taxa do aparelho": (
                st.column_config.NumberColumn(
                    "Taxa do aparelho",
                    format="R$ %.2f",
                )
            ),
            "Valor médico": (
                st.column_config.NumberColumn(
                    "Valor médico",
                    format="R$ %.2f",
                )
            ),
        },
    )