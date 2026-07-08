from calendar import monthrange
from datetime import date
import re
import unicodedata

import pandas as pd
import streamlit as st

from auxiliar.google_sheets import get_sheet_data


NOME_ABA_BASE_DADOS = "base_dados"
NOME_ABA_MEDICOS = "lista_medicos"
NOME_ABA_SOBREAVISO = "base_sobreaviso"
NOME_ABA_MEIO_PERIODO = "base_meio_periodo"

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

    texto = re.sub(
        r"[R$\s]",
        "",
        texto,
    )

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
            linhas_invalidas.append(
                indice + 2
            )

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


def converter_coluna_data(
    serie: pd.Series,
) -> pd.Series:
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


def normalizar_texto(valor: str) -> str:
    """
    Normaliza textos para facilitar o cruzamento entre
    nomes de médicos das diferentes bases.
    """
    texto = str(valor).strip().lower()

    texto = unicodedata.normalize(
        "NFKD",
        texto,
    )

    texto = (
        texto
        .encode("ascii", "ignore")
        .decode("ascii")
    )

    texto = texto.replace("_", " ")
    texto = texto.replace("-", " ")

    texto = re.sub(
        r"\s+",
        " ",
        texto,
    )

    return texto.strip()


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
    total_sobreaviso: float,
    total_final_medico: float,
) -> None:
    """
    Exibe os totais financeiros do período.
    """
    st.markdown(
        "### Totais do período"
    )

    (
        coluna_1,
        coluna_2,
        coluna_3,
        coluna_4,
        coluna_5,
    ) = st.columns(5)

    with coluna_1:
        st.metric(
            "Total dos exames",
            formatar_moeda(
                total_exames
            ),
        )

    with coluna_2:
        st.metric(
            "Total taxa aparelho",
            formatar_moeda(
                total_taxa_aparelho
            ),
        )

    with coluna_3:
        st.metric(
            "Total médico",
            formatar_moeda(
                total_medico
            ),
            help=(
                "Total antes da aplicação do "
                "valor mínimo."
            ),
        )

    with coluna_4:
        st.metric(
            "Total sobreaviso",
            formatar_moeda(
                total_sobreaviso
            ),
            help=(
                "Soma dos sobreavisos registrados "
                "no período."
            ),
        )

    with coluna_5:
        st.metric(
            "Total final médico",
            formatar_moeda(
                total_final_medico
            ),
            help=(
                "Total após a aplicação do valor mínimo diário "
                "e a soma dos sobreavisos."
            ),
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
        st.markdown(
            "# 💰"
        )

    with coluna_titulo:
        st.title(
            "Controle financeiro"
        )

        st.caption(
            "ARLONSP - SERVIÇOS MÉDICOS | "
            "Resumo financeiro dos atendimentos"
        )


# ============================================================
# Carregamento dos dados
# ============================================================

try:
    with st.spinner(
        "Carregando dados financeiros..."
    ):
        base_dados_df = get_sheet_data(
            NOME_ABA_BASE_DADOS
        ).copy()

        lista_medicos_df = get_sheet_data(
            NOME_ABA_MEDICOS
        ).copy()

        base_sobreaviso_df = get_sheet_data(
            NOME_ABA_SOBREAVISO
        ).copy()

        base_meio_periodo_df = get_sheet_data(
            NOME_ABA_MEIO_PERIODO
        ).copy()

except Exception as error:
    st.error(
        "Não foi possível carregar os dados das planilhas."
    )

    st.exception(error)
    st.stop()


# Caso a aba esteja completamente vazia, preserva
# a estrutura esperada.
if (
    base_meio_periodo_df.empty
    and len(base_meio_periodo_df.columns) == 0
):
    base_meio_periodo_df = pd.DataFrame(
        columns=[
            "data",
            "medico",
        ]
    )


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

base_sobreaviso_df.columns = (
    base_sobreaviso_df.columns
    .astype(str)
    .str.strip()
)

base_meio_periodo_df.columns = (
    base_meio_periodo_df.columns
    .astype(str)
    .str.strip()
)


# ============================================================
# Validação das estruturas
# ============================================================

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

    validar_colunas(
        base_sobreaviso_df,
        NOME_ABA_SOBREAVISO,
        [
            "data",
            "medico",
            "valor",
        ],
    )

    validar_colunas(
        base_meio_periodo_df,
        NOME_ABA_MEIO_PERIODO,
        [
            "data",
            "medico",
        ],
    )

except ValueError as error:
    st.error(
        str(error)
    )

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

lista_medicos_df["medico_normalizado"] = (
    lista_medicos_df["nome_medico"]
    .apply(normalizar_texto)
)


lista_medicos_df = lista_medicos_df.loc[
    lista_medicos_df[
        "medico_normalizado"
    ].ne("")
].copy()


try:
    lista_medicos_df["valor_minimo"] = (
        converter_coluna_monetaria(
            lista_medicos_df["valor_minimo"],
            "valor_minimo",
        )
    )

except ValueError as error:
    st.error(
        str(error)
    )

    st.stop()


medicos_duplicados = (
    lista_medicos_df.loc[
        lista_medicos_df[
            "medico_normalizado"
        ].duplicated(
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
        + ", ".join(
            medicos_duplicados
        )
    )


lista_medicos_df = (
    lista_medicos_df
    .drop_duplicates(
        subset=[
            "medico_normalizado",
        ],
        keep="last",
    )
    [
        [
            "nome_medico",
            "medico_normalizado",
            "valor_minimo",
        ]
    ]
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

base_dados_df["medico_normalizado"] = (
    base_dados_df["nome_medico"]
    .apply(normalizar_texto)
)

base_dados_df["data_convertida"] = (
    converter_coluna_data(
        base_dados_df["data"]
    )
)


quantidade_datas_invalidas = int(
    base_dados_df[
        "data_convertida"
    ]
    .isna()
    .sum()
)


if quantidade_datas_invalidas:
    st.warning(
        f"{quantidade_datas_invalidas} registro(s) da base de "
        "atendimentos possuem uma data inválida e não serão "
        "considerados nos cálculos."
    )


base_dados_df = base_dados_df.loc[
    base_dados_df["data_convertida"].notna()
    & base_dados_df["medico_normalizado"].ne("")
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
    st.error(
        str(error)
    )

    st.stop()


# ============================================================
# Tratamento da base de sobreaviso
# ============================================================

base_sobreaviso_df["medico"] = (
    base_sobreaviso_df["medico"]
    .fillna("")
    .astype(str)
    .str.strip()
)

base_sobreaviso_df["medico_normalizado"] = (
    base_sobreaviso_df["medico"]
    .apply(normalizar_texto)
)

base_sobreaviso_df["data_convertida"] = (
    converter_coluna_data(
        base_sobreaviso_df["data"]
    )
)


quantidade_datas_sobreaviso_invalidas = int(
    base_sobreaviso_df[
        "data_convertida"
    ]
    .isna()
    .sum()
)


if quantidade_datas_sobreaviso_invalidas:
    st.warning(
        f"{quantidade_datas_sobreaviso_invalidas} registro(s) "
        "da base de sobreaviso possuem uma data inválida e não "
        "serão considerados nos cálculos."
    )


base_sobreaviso_df = base_sobreaviso_df.loc[
    base_sobreaviso_df["data_convertida"].notna()
    & base_sobreaviso_df["medico_normalizado"].ne("")
].copy()


try:
    base_sobreaviso_df["valor"] = (
        converter_coluna_monetaria(
            base_sobreaviso_df["valor"],
            "valor da base_sobreaviso",
        )
    )

except ValueError as error:
    st.error(
        str(error)
    )

    st.stop()


base_sobreaviso_df = (
    base_sobreaviso_df.rename(
        columns={
            "medico": "nome_medico",
            "valor": "valor_sobreaviso",
        }
    )
)


# ============================================================
# Tratamento da base de meio período
# ============================================================

base_meio_periodo_df["medico"] = (
    base_meio_periodo_df["medico"]
    .fillna("")
    .astype(str)
    .str.strip()
)

base_meio_periodo_df["medico_normalizado"] = (
    base_meio_periodo_df["medico"]
    .apply(normalizar_texto)
)

base_meio_periodo_df["data_convertida"] = (
    converter_coluna_data(
        base_meio_periodo_df["data"]
    )
)


quantidade_datas_meio_periodo_invalidas = int(
    base_meio_periodo_df[
        "data_convertida"
    ]
    .isna()
    .sum()
)


if quantidade_datas_meio_periodo_invalidas:
    st.warning(
        f"{quantidade_datas_meio_periodo_invalidas} registro(s) "
        "da base de meio período possuem uma data inválida e "
        "não serão considerados nos cálculos."
    )


base_meio_periodo_df = (
    base_meio_periodo_df.loc[
        base_meio_periodo_df[
            "data_convertida"
        ].notna()
        & base_meio_periodo_df[
            "medico_normalizado"
        ].ne("")
    ]
    .copy()
)


duplicidades_meio_periodo = (
    base_meio_periodo_df
    .duplicated(
        subset=[
            "data_convertida",
            "medico_normalizado",
        ],
        keep=False,
    )
    .sum()
)


if duplicidades_meio_periodo:
    st.warning(
        "Existem registros duplicados na aba "
        "`base_meio_periodo`. As duplicidades serão "
        "consideradas apenas uma vez."
    )


base_meio_periodo_df = (
    base_meio_periodo_df
    .drop_duplicates(
        subset=[
            "data_convertida",
            "medico_normalizado",
        ],
        keep="last",
    )
    [
        [
            "data_convertida",
            "medico_normalizado",
        ]
    ]
    .copy()
)


base_meio_periodo_df["meio_periodo"] = True


# ============================================================
# Período padrão: mês atual
# ============================================================

hoje = date.today()

primeiro_dia_mes = hoje.replace(
    day=1
)

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

medicos_com_sobreaviso = (
    base_sobreaviso_df["nome_medico"]
    .dropna()
    .astype(str)
    .str.strip()
    .tolist()
)


opcoes_medicos = sorted(
    (
        set(medicos_cadastrados)
        | set(medicos_com_atendimento)
        | set(medicos_com_sobreaviso)
    ),
    key=normalizar_texto,
)


with st.container(border=True):
    st.markdown(
        "### Filtros"
    )

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


data_inicial_timestamp = pd.Timestamp(
    data_inicial
).normalize()

data_final_timestamp = pd.Timestamp(
    data_final
).normalize()


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


sobreaviso_filtrado_df = base_sobreaviso_df.loc[
    base_sobreaviso_df["data_convertida"].between(
        data_inicial_timestamp,
        data_final_timestamp,
        inclusive="both",
    )
].copy()


if medico_selecionado != TODOS_OS_MEDICOS:
    medico_selecionado_normalizado = normalizar_texto(
        medico_selecionado
    )

    base_filtrada_df = base_filtrada_df.loc[
        base_filtrada_df[
            "medico_normalizado"
        ].eq(
            medico_selecionado_normalizado
        )
    ].copy()

    sobreaviso_filtrado_df = (
        sobreaviso_filtrado_df.loc[
            sobreaviso_filtrado_df[
                "medico_normalizado"
            ].eq(
                medico_selecionado_normalizado
            )
        ]
        .copy()
    )


# ============================================================
# Agrupamento dos atendimentos por dia e médico
# ============================================================

if base_filtrada_df.empty:
    resumo_atendimentos_df = pd.DataFrame(
        columns=[
            "data_convertida",
            "medico_normalizado",
            "nome_medico",
            "valor_exame",
            "taxa_aparelho",
            "valor_medico",
            "quantidade_atendimentos",
        ]
    )

else:
    resumo_atendimentos_df = (
        base_filtrada_df
        .groupby(
            [
                "data_convertida",
                "medico_normalizado",
            ],
            as_index=False,
        )
        .agg(
            nome_medico=(
                "nome_medico",
                "first",
            ),
            valor_exame=(
                "valor_exame",
                "sum",
            ),
            taxa_aparelho=(
                "taxa_aparelho",
                "sum",
            ),
            valor_medico=(
                "valor_medico",
                "sum",
            ),
            quantidade_atendimentos=(
                "valor_medico",
                "size",
            ),
        )
    )


# ============================================================
# Agrupamento dos sobreavisos por dia e médico
# ============================================================

if sobreaviso_filtrado_df.empty:
    resumo_sobreaviso_df = pd.DataFrame(
        columns=[
            "data_convertida",
            "medico_normalizado",
            "nome_medico",
            "valor_sobreaviso",
        ]
    )

else:
    resumo_sobreaviso_df = (
        sobreaviso_filtrado_df
        .groupby(
            [
                "data_convertida",
                "medico_normalizado",
            ],
            as_index=False,
        )
        .agg(
            nome_medico=(
                "nome_medico",
                "first",
            ),
            valor_sobreaviso=(
                "valor_sobreaviso",
                "sum",
            ),
        )
    )


# ============================================================
# União dos atendimentos e sobreavisos
# ============================================================

resumo_financeiro_df = resumo_atendimentos_df.merge(
    resumo_sobreaviso_df,
    how="outer",
    on=[
        "data_convertida",
        "medico_normalizado",
    ],
    suffixes=(
        "_atendimento",
        "_sobreaviso",
    ),
)


if resumo_financeiro_df.empty:
    exibir_cards(
        total_exames=0,
        total_taxa_aparelho=0,
        total_medico=0,
        total_sobreaviso=0,
        total_final_medico=0,
    )

    st.info(
        "Nenhum atendimento ou sobreaviso foi encontrado "
        "para os filtros selecionados."
    )

    st.stop()


resumo_financeiro_df["nome_medico"] = (
    resumo_financeiro_df[
        "nome_medico_atendimento"
    ]
    .fillna(
        resumo_financeiro_df[
            "nome_medico_sobreaviso"
        ]
    )
)


resumo_financeiro_df = (
    resumo_financeiro_df.drop(
        columns=[
            "nome_medico_atendimento",
            "nome_medico_sobreaviso",
        ]
    )
)


colunas_para_preencher = [
    "valor_exame",
    "taxa_aparelho",
    "valor_medico",
    "quantidade_atendimentos",
    "valor_sobreaviso",
]


for coluna in colunas_para_preencher:
    resumo_financeiro_df[coluna] = (
        resumo_financeiro_df[coluna]
        .fillna(0)
    )


resumo_financeiro_df[
    "quantidade_atendimentos"
] = (
    resumo_financeiro_df[
        "quantidade_atendimentos"
    ]
    .astype(int)
)


# ============================================================
# Inclusão do valor mínimo cadastrado
# ============================================================

resumo_financeiro_df = resumo_financeiro_df.merge(
    lista_medicos_df[
        [
            "medico_normalizado",
            "valor_minimo",
        ]
    ],
    how="left",
    on="medico_normalizado",
)


medicos_sem_valor_minimo = (
    resumo_financeiro_df.loc[
        resumo_financeiro_df[
            "valor_minimo"
        ].isna(),
        "nome_medico",
    ]
    .drop_duplicates()
    .tolist()
)


if medicos_sem_valor_minimo:
    st.warning(
        "Os seguintes médicos não possuem valor mínimo "
        "cadastrado e utilizarão R$ 0,00: "
        + ", ".join(
            medicos_sem_valor_minimo
        )
    )


resumo_financeiro_df["valor_minimo"] = (
    resumo_financeiro_df["valor_minimo"]
    .fillna(0.0)
    .astype(float)
)


# ============================================================
# Cruzamento com a base de meio período
# ============================================================

resumo_financeiro_df = resumo_financeiro_df.merge(
    base_meio_periodo_df,
    how="left",
    on=[
        "data_convertida",
        "medico_normalizado",
    ],
)


resumo_financeiro_df["meio_periodo"] = (
    resumo_financeiro_df["meio_periodo"]
    .fillna(False)
    .astype(bool)
)


tem_atendimento = (
    resumo_financeiro_df[
        "quantidade_atendimentos"
    ] > 0
)


# O valor cadastrado em lista_medicos representa
# o valor mínimo para dois períodos.
#
# Quando a data está na base_meio_periodo, utiliza metade.
resumo_financeiro_df[
    "valor_minimo_utilizado"
] = resumo_financeiro_df["valor_minimo"]


resumo_financeiro_df.loc[
    resumo_financeiro_df["meio_periodo"],
    "valor_minimo_utilizado",
] = (
    resumo_financeiro_df.loc[
        resumo_financeiro_df["meio_periodo"],
        "valor_minimo",
    ]
    / 2
)


# Quando existe somente sobreaviso, sem atendimento,
# nenhum valor mínimo é aplicado.
resumo_financeiro_df[
    "valor_minimo_utilizado"
] = (
    resumo_financeiro_df[
        "valor_minimo_utilizado"
    ]
    .where(
        tem_atendimento,
        0.0,
    )
)


# ============================================================
# Aplicação do valor mínimo
# ============================================================

resumo_financeiro_df[
    "pagar_valor_minimo"
] = (
    tem_atendimento
    & (
        resumo_financeiro_df[
            "valor_medico"
        ]
        < resumo_financeiro_df[
            "valor_minimo_utilizado"
        ]
    )
)


resumo_financeiro_df[
    "valor_apos_minimo"
] = (
    resumo_financeiro_df[
        [
            "valor_medico",
            "valor_minimo_utilizado",
        ]
    ]
    .max(axis=1)
)


resumo_financeiro_df[
    "valor_apos_minimo"
] = (
    resumo_financeiro_df[
        "valor_apos_minimo"
    ]
    .where(
        tem_atendimento,
        0.0,
    )
)


# Depois de aplicar o valor mínimo, acrescenta o sobreaviso.
resumo_financeiro_df[
    "valor_final_medico"
] = (
    resumo_financeiro_df[
        "valor_apos_minimo"
    ]
    + resumo_financeiro_df[
        "valor_sobreaviso"
    ]
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

total_sobreaviso = resumo_financeiro_df[
    "valor_sobreaviso"
].sum()

total_final_medico = resumo_financeiro_df[
    "valor_final_medico"
].sum()


exibir_cards(
    total_exames=total_exames,
    total_taxa_aparelho=total_taxa_aparelho,
    total_medico=total_medico,
    total_sobreaviso=total_sobreaviso,
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
        "meio_periodo",
        "valor_minimo_utilizado",
        "pagar_valor_minimo",
        "valor_sobreaviso",
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
        "meio_periodo": "Meio período",
        "valor_minimo_utilizado": (
            "Valor mínimo utilizado"
        ),
        "pagar_valor_minimo": (
            "Pagar valor mínimo"
        ),
        "valor_sobreaviso": (
            "Valor sobreaviso"
        ),
        "valor_final_medico": (
            "Valor final médico"
        ),
    }
)


tabela_exibicao_df["Data"] = (
    tabela_exibicao_df["Data"]
    .dt.date
)


st.markdown(
    "### Detalhamento diário por médico"
)

st.caption(
    f"Período de {data_inicial.strftime('%d/%m/%Y')} "
    f"até {data_final.strftime('%d/%m/%Y')}. "
    "O valor mínimo é reduzido pela metade nos dias "
    "marcados como meio período."
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
        "Valor dos exames": (
            st.column_config.NumberColumn(
                "Valor dos exames",
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
                help=(
                    "Valor calculado antes da aplicação "
                    "do mínimo."
                ),
            )
        ),
        "Meio período": (
            st.column_config.CheckboxColumn(
                "Meio período",
                help=(
                    "Marcado quando a data e o médico estão "
                    "cadastrados na aba base_meio_periodo."
                ),
            )
        ),
        "Valor mínimo utilizado": (
            st.column_config.NumberColumn(
                "Valor mínimo utilizado",
                format="R$ %.2f",
                help=(
                    "Valor mínimo completo para dois períodos "
                    "ou metade do valor nos dias marcados como "
                    "meio período."
                ),
            )
        ),
        "Pagar valor mínimo": (
            st.column_config.CheckboxColumn(
                "Pagar valor mínimo",
                help=(
                    "Marcado quando o valor diário calculado "
                    "para o médico é menor que o valor mínimo "
                    "utilizado naquele dia."
                ),
            )
        ),
        "Valor sobreaviso": (
            st.column_config.NumberColumn(
                "Valor sobreaviso",
                format="R$ %.2f",
                help=(
                    "Soma dos sobreavisos registrados para "
                    "o médico na data."
                ),
            )
        ),
        "Valor final médico": (
            st.column_config.NumberColumn(
                "Valor final médico",
                format="R$ %.2f",
                help=(
                    "Valor após a aplicação do mínimo diário, "
                    "acrescido do valor de sobreaviso."
                ),
            )
        ),
    },
)