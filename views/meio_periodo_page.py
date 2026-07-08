from datetime import date
import re
import unicodedata

import pandas as pd
import streamlit as st

from auxiliar.google_sheets import (
    get_sheet_data,
    set_sheet_data,
)


NOME_ABA_BASE_DADOS = "base_dados"
NOME_ABA_MEIO_PERIODO = "base_meio_periodo"


# ============================================================
# Funções auxiliares
# ============================================================

def normalizar_texto(valor: str) -> str:
    """
    Remove acentos, diferenças entre maiúsculas e minúsculas,
    espaços duplicados, hífens e underlines.
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
    Valida se as colunas obrigatórias existem na planilha.
    """
    colunas_ausentes = [
        coluna
        for coluna in colunas_obrigatorias
        if coluna not in dataframe.columns
    ]

    if colunas_ausentes:
        raise ValueError(
            f"A aba '{nome_aba}' não possui as colunas: "
            f"{', '.join(colunas_ausentes)}"
        )


def converter_coluna_data(
    serie: pd.Series,
) -> pd.Series:
    """
    Converte datas nos formatos mais comuns utilizados
    pelo sistema.
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


def obter_lista_medicos(
    base_dados_df: pd.DataFrame,
) -> list[str]:
    """
    Retorna os médicos que possuem atendimentos na base,
    sem duplicidades e em ordem alfabética.
    """
    medicos = (
        base_dados_df["nome_medico"]
        .dropna()
        .astype(str)
        .str.strip()
    )

    medicos = medicos.loc[
        medicos.ne("")
    ]

    medicos_unicos = (
        medicos
        .drop_duplicates()
        .tolist()
    )

    return sorted(
        medicos_unicos,
        key=normalizar_texto,
    )


def preparar_base_meio_periodo(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Prepara a base de meio período e cria as colunas
    auxiliares utilizadas no cruzamento.
    """
    dataframe = dataframe.copy()

    if dataframe.empty and len(dataframe.columns) == 0:
        dataframe = pd.DataFrame(
            columns=[
                "data",
                "medico",
            ]
        )

    dataframe.columns = (
        dataframe.columns
        .astype(str)
        .str.strip()
    )

    validar_colunas(
        dataframe,
        NOME_ABA_MEIO_PERIODO,
        [
            "data",
            "medico",
        ],
    )

    dataframe = dataframe[
        [
            "data",
            "medico",
        ]
    ].copy()

    dataframe["data_convertida"] = converter_coluna_data(
        dataframe["data"]
    )

    dataframe["medico"] = (
        dataframe["medico"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    dataframe["medico_normalizado"] = (
        dataframe["medico"]
        .apply(normalizar_texto)
    )

    return dataframe


def montar_base_final(
    base_meio_periodo_df: pd.DataFrame,
    medico_selecionado: str,
    datas_exibidas: set[pd.Timestamp],
    datas_marcadas: set[pd.Timestamp],
) -> pd.DataFrame:
    """
    Atualiza somente os registros do médico e das datas
    atualmente exibidas.

    Registros de outros médicos e de outros períodos
    permanecem inalterados.
    """
    base_atual = base_meio_periodo_df.copy()

    medico_normalizado = normalizar_texto(
        medico_selecionado
    )

    mascara_registros_exibidos = (
        base_atual["medico_normalizado"].eq(
            medico_normalizado
        )
        & base_atual["data_convertida"].isin(
            datas_exibidas
        )
    )

    # Remove da base os registros das datas que estão
    # sendo editadas. Depois, apenas as datas marcadas
    # serão inseridas novamente.
    base_preservada = base_atual.loc[
        ~mascara_registros_exibidos,
        [
            "data",
            "medico",
        ],
    ].copy()

    novos_registros = pd.DataFrame(
        [
            {
                "data": data_meio_periodo.strftime(
                    "%d/%m/%Y"
                ),
                "medico": medico_selecionado,
            }
            for data_meio_periodo in sorted(
                datas_marcadas
            )
        ],
        columns=[
            "data",
            "medico",
        ],
    )

    base_final = pd.concat(
        [
            base_preservada,
            novos_registros,
        ],
        ignore_index=True,
    )

    if base_final.empty:
        return pd.DataFrame(
            columns=[
                "data",
                "medico",
            ]
        )

    base_final["data_convertida"] = converter_coluna_data(
        base_final["data"]
    )

    base_final["medico"] = (
        base_final["medico"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    base_final["medico_normalizado"] = (
        base_final["medico"]
        .apply(normalizar_texto)
    )

    registros_validos = base_final.loc[
        base_final["data_convertida"].notna()
        & base_final["medico_normalizado"].ne("")
    ].copy()

    registros_invalidos = base_final.loc[
        base_final["data_convertida"].isna()
        | base_final["medico_normalizado"].eq("")
    ].copy()

    # Evita registros duplicados do mesmo médico
    # na mesma data.
    registros_validos = (
        registros_validos
        .drop_duplicates(
            subset=[
                "data_convertida",
                "medico_normalizado",
            ],
            keep="last",
        )
        .sort_values(
            [
                "data_convertida",
                "medico_normalizado",
            ]
        )
        .reset_index(drop=True)
    )

    registros_validos["data"] = (
        registros_validos["data_convertida"]
        .dt.strftime("%d/%m/%Y")
    )

    base_final = pd.concat(
        [
            registros_validos[
                [
                    "data",
                    "medico",
                ]
            ],
            registros_invalidos[
                [
                    "data",
                    "medico",
                ]
            ],
        ],
        ignore_index=True,
    )

    base_final = base_final.where(
        pd.notna(base_final),
        "",
    )

    return base_final[
        [
            "data",
            "medico",
        ]
    ]


# ============================================================
# Mensagem após salvar
# ============================================================

mensagem_sucesso = st.session_state.pop(
    "mensagem_meio_periodo_salva",
    None,
)


if mensagem_sucesso:
    st.success(
        mensagem_sucesso
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
        st.markdown("# 🌓")

    with coluna_titulo:
        st.title(
            "Configuração de meio período"
        )

        st.caption(
            "Marque os dias em que o médico trabalhou "
            "somente meio período."
        )


st.info(
    "Por padrão, o sistema considera que o médico trabalhou "
    "dois períodos. Marque somente as datas que devem utilizar "
    "metade do valor mínimo diário."
)


# ============================================================
# Carregamento das bases
# ============================================================

try:
    with st.spinner(
        "Carregando atendimentos e configurações..."
    ):
        base_dados_df = get_sheet_data(
            NOME_ABA_BASE_DADOS
        ).copy()

        base_meio_periodo_original_df = get_sheet_data(
            NOME_ABA_MEIO_PERIODO
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


try:
    validar_colunas(
        base_dados_df,
        NOME_ABA_BASE_DADOS,
        [
            "data",
            "nome_medico",
        ],
    )

    base_meio_periodo_df = preparar_base_meio_periodo(
        base_meio_periodo_original_df
    )

except ValueError as error:
    st.error(
        str(error)
    )

    st.stop()


# ============================================================
# Preparação da base de atendimentos
# ============================================================

base_dados_df["data_convertida"] = converter_coluna_data(
    base_dados_df["data"]
)

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


quantidade_datas_invalidas = int(
    base_dados_df["data_convertida"]
    .isna()
    .sum()
)


if quantidade_datas_invalidas > 0:
    st.warning(
        f"{quantidade_datas_invalidas} registro(s) da "
        f"aba `{NOME_ABA_BASE_DADOS}` possuem data inválida "
        "e não serão considerados nesta página."
    )


base_dados_valida_df = base_dados_df.loc[
    base_dados_df["data_convertida"].notna()
    & base_dados_df["medico_normalizado"].ne("")
].copy()


medicos_disponiveis = obter_lista_medicos(
    base_dados_valida_df
)


if not medicos_disponiveis:
    st.warning(
        "Nenhum médico com atendimento válido foi encontrado "
        f"na aba `{NOME_ABA_BASE_DADOS}`."
    )

    st.stop()


# ============================================================
# Filtros
# ============================================================

hoje = date.today()

primeiro_dia_mes = hoje.replace(
    day=1
)


with st.container(border=True):
    st.markdown(
        "### Selecione o período e o médico"
    )

    coluna_periodo, coluna_medico = st.columns(2)

    with coluna_periodo:
        periodo_selecionado = st.date_input(
            "Período dos atendimentos",
            value=(
                primeiro_dia_mes,
                hoje,
            ),
            format="DD/MM/YYYY",
        )

    with coluna_medico:
        medico_selecionado = st.selectbox(
            "Médico",
            options=medicos_disponiveis,
            index=None,
            placeholder="Selecione um médico",
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


data_inicial = pd.Timestamp(
    periodo_selecionado[0]
).normalize()

data_final = pd.Timestamp(
    periodo_selecionado[1]
).normalize()


if data_inicial > data_final:
    st.error(
        "A data inicial não pode ser posterior à data final."
    )

    st.stop()


if not medico_selecionado:
    st.info(
        "Selecione um médico para visualizar os dias "
        "com atendimento."
    )

    st.stop()


# ============================================================
# Dias de atendimento do médico
# ============================================================

medico_selecionado_normalizado = normalizar_texto(
    medico_selecionado
)


dias_atendimento_df = base_dados_valida_df.loc[
    base_dados_valida_df["medico_normalizado"].eq(
        medico_selecionado_normalizado
    )
    & base_dados_valida_df["data_convertida"].between(
        data_inicial,
        data_final,
    ),
    [
        "data_convertida",
    ],
].copy()


# Um atendimento pode possuir várias linhas por causa
# dos exames e procedimentos. Por isso, mostramos apenas
# uma linha por data.
dias_atendimento_df = (
    dias_atendimento_df
    .drop_duplicates(
        subset=[
            "data_convertida",
        ]
    )
    .sort_values(
        "data_convertida"
    )
    .reset_index(drop=True)
)


if dias_atendimento_df.empty:
    st.warning(
        "Esse médico não possui atendimentos no período "
        "selecionado."
    )

    st.stop()


datas_meio_periodo_salvas = set(
    base_meio_periodo_df.loc[
        base_meio_periodo_df[
            "medico_normalizado"
        ].eq(
            medico_selecionado_normalizado
        )
        & base_meio_periodo_df[
            "data_convertida"
        ].notna(),
        "data_convertida",
    ].tolist()
)


tabela_edicao_df = pd.DataFrame(
    {
        "Data": (
            dias_atendimento_df[
                "data_convertida"
            ].dt.date
        ),
        "Meio período": (
            dias_atendimento_df[
                "data_convertida"
            ].isin(
                datas_meio_periodo_salvas
            )
        ),
    }
)


# ============================================================
# Tabela editável
# ============================================================

st.markdown(
    "### Dias com atendimento"
)

st.caption(
    "Marque somente os dias em que o médico trabalhou "
    "meio período. Dias desmarcados serão considerados "
    "como dois períodos."
)


chave_editor = (
    "editor_meio_periodo_"
    f"{medico_selecionado_normalizado}_"
    f"{data_inicial.strftime('%Y%m%d')}_"
    f"{data_final.strftime('%Y%m%d')}"
)


tabela_editada_df = st.data_editor(
    tabela_edicao_df,
    use_container_width=True,
    hide_index=True,
    disabled=[
        "Data",
    ],
    column_config={
        "Data": st.column_config.DateColumn(
            "Data",
            format="DD/MM/YYYY",
        ),
        "Meio período": st.column_config.CheckboxColumn(
            "Meio período",
            help=(
                "Marque quando o médico trabalhou "
                "somente meio período."
            ),
            default=False,
        ),
    },
    key=chave_editor,
)


quantidade_dias = len(
    tabela_editada_df
)

quantidade_meio_periodo = int(
    tabela_editada_df["Meio período"]
    .fillna(False)
    .astype(bool)
    .sum()
)


coluna_dias, coluna_meio_periodo = st.columns(2)

with coluna_dias:
    st.metric(
        "Dias com atendimento",
        quantidade_dias,
    )

with coluna_meio_periodo:
    st.metric(
        "Dias marcados como meio período",
        quantidade_meio_periodo,
    )


# ============================================================
# Salvamento
# ============================================================

st.warning(
    "Ao salvar, as marcações exibidas acima serão "
    "sincronizadas com a aba `base_meio_periodo`."
)


salvar_alteracoes = st.button(
    "💾 Salvar marcações",
    type="primary",
    use_container_width=True,
)


if salvar_alteracoes:
    tabela_para_salvar_df = (
        tabela_editada_df.copy()
    )

    tabela_para_salvar_df[
        "data_convertida"
    ] = pd.to_datetime(
        tabela_para_salvar_df["Data"],
        errors="coerce",
    ).dt.normalize()

    datas_exibidas = set(
        tabela_para_salvar_df.loc[
            tabela_para_salvar_df[
                "data_convertida"
            ].notna(),
            "data_convertida",
        ].tolist()
    )

    datas_marcadas = set(
        tabela_para_salvar_df.loc[
            tabela_para_salvar_df[
                "data_convertida"
            ].notna()
            & tabela_para_salvar_df[
                "Meio período"
            ].fillna(False).astype(bool),
            "data_convertida",
        ].tolist()
    )

    try:
        base_final_df = montar_base_final(
            base_meio_periodo_df=base_meio_periodo_df,
            medico_selecionado=medico_selecionado,
            datas_exibidas=datas_exibidas,
            datas_marcadas=datas_marcadas,
        )

        with st.spinner(
            "Salvando marcações..."
        ):
            set_sheet_data(
                NOME_ABA_MEIO_PERIODO,
                base_final_df,
            )

        st.session_state[
            "mensagem_meio_periodo_salva"
        ] = (
            f"As marcações de meio período de "
            f"{medico_selecionado} foram salvas com sucesso."
        )

        st.rerun()

    except Exception as error:
        st.error(
            "Não foi possível salvar as marcações "
            "de meio período."
        )

        st.exception(error)