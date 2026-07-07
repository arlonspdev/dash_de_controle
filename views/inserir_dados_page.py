from datetime import date
import re
import unicodedata

import pandas as pd
import streamlit as st

from auxiliar.google_sheets import (
    append_sheet_data,
    get_sheet_data,
)


NOME_ABA_EXAMES = "lista_exames"
NOME_ABA_MEDICOS = "lista_medicos"
NOME_ABA_PROCEDIMENTOS = "lista_procedimentos"
NOME_ABA_CONVENIOS = "lista_convenios"
NOME_ABA_OUTROS_VALORES = "outros_valores"
NOME_ABA_BASE_DADOS = "base_dados"


# ============================================================
# Funções auxiliares
# ============================================================

def formatar_moeda(valor: float) -> str:
    """
    Formata um número no padrão brasileiro.

    Exemplo:
        1234.5 -> R$ 1.234,50
    """
    valor_formatado = f"{valor:,.2f}"

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

    texto = re.sub(
        r"[R$\s]",
        "",
        texto,
    )

    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "")
            texto = texto.replace(",", ".")

        else:
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
    Remove acentos, espaços extras e diferenças entre
    hífen, underline e espaço.
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
    Verifica se todas as colunas necessárias existem.
    """
    colunas_ausentes = [
        coluna
        for coluna in colunas_obrigatorias
        if coluna not in dataframe.columns
    ]

    if colunas_ausentes:
        raise ValueError(
            f"A aba '{nome_aba}' não possui as seguintes colunas: "
            f"{', '.join(colunas_ausentes)}"
        )


def obter_lista_unica(
    dataframe: pd.DataFrame,
    nome_coluna: str,
) -> list[str]:
    """
    Retorna valores preenchidos e únicos de uma coluna,
    preservando a ordem da planilha.
    """
    valores = (
        dataframe[nome_coluna]
        .dropna()
        .astype(str)
        .str.strip()
    )

    valores = valores.loc[
        valores.ne("")
    ]

    return (
        valores
        .drop_duplicates()
        .tolist()
    )


def formatar_procedimentos(
    procedimentos_selecionados: list[str],
) -> str:
    """
    Formata a lista de procedimentos para ser salva
    em uma única célula.

    Exemplo:
        ["Polipectomia", "Mucosectomia"]

    Resultado:
        "+Polipectomia +Mucosectomia"
    """
    procedimentos_formatados = []

    for procedimento in procedimentos_selecionados:
        procedimento_limpo = (
            str(procedimento)
            .strip()
            .lstrip("+")
            .strip()
        )

        if procedimento_limpo:
            procedimentos_formatados.append(
                f"+{procedimento_limpo}"
            )

    return " ".join(
        procedimentos_formatados
    )


def obter_taxa_aparelho(
    dataframe: pd.DataFrame,
) -> tuple[float, bool]:
    """
    Busca a descrição taxa_aparelho na aba outros_valores.
    """
    if dataframe.empty:
        return 0.0, False

    base = dataframe.copy()

    base["descricao_normalizada"] = (
        base["descricao"]
        .fillna("")
        .apply(normalizar_texto)
    )

    resultado = base.loc[
        base["descricao_normalizada"].eq(
            "taxa aparelho"
        )
    ]

    if resultado.empty:
        return 0.0, False

    valor = converter_para_float(
        resultado.iloc[0]["valor"]
    )

    return valor, True


# ============================================================
# Estado da página
# ============================================================

if "versao_formulario_atendimento" not in st.session_state:
    st.session_state[
        "versao_formulario_atendimento"
    ] = 0


mensagem_sucesso = st.session_state.pop(
    "mensagem_sucesso_atendimento",
    None,
)


if mensagem_sucesso:
    st.success(
        mensagem_sucesso
    )


versao_formulario = st.session_state[
    "versao_formulario_atendimento"
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
        st.markdown("# 🩺")

    with coluna_titulo:
        st.title(
            "ARLONSP - SERVIÇOS MÉDICOS"
        )

        st.caption(
            "Registro de atendimentos e utilização "
            "do equipamento"
        )


st.subheader(
    "Inserir novo atendimento"
)


# ============================================================
# Carregamento das planilhas
# ============================================================

try:
    with st.spinner(
        "Carregando médicos, exames, convênios "
        "e procedimentos..."
    ):
        lista_exames_df = get_sheet_data(
            NOME_ABA_EXAMES
        ).copy()

        lista_medicos_df = get_sheet_data(
            NOME_ABA_MEDICOS
        ).copy()

        lista_procedimentos_df = get_sheet_data(
            NOME_ABA_PROCEDIMENTOS
        ).copy()

        lista_convenios_df = get_sheet_data(
            NOME_ABA_CONVENIOS
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


# Remove espaços acidentais dos nomes das colunas.
lista_exames_df.columns = (
    lista_exames_df.columns
    .astype(str)
    .str.strip()
)

lista_medicos_df.columns = (
    lista_medicos_df.columns
    .astype(str)
    .str.strip()
)

lista_procedimentos_df.columns = (
    lista_procedimentos_df.columns
    .astype(str)
    .str.strip()
)

lista_convenios_df.columns = (
    lista_convenios_df.columns
    .astype(str)
    .str.strip()
)

outros_valores_df.columns = (
    outros_valores_df.columns
    .astype(str)
    .str.strip()
)


# ============================================================
# Validação das estruturas
# ============================================================

try:
    validar_colunas(
        lista_exames_df,
        NOME_ABA_EXAMES,
        [
            "nome_exame",
            "valor_exame",
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
        lista_procedimentos_df,
        NOME_ABA_PROCEDIMENTOS,
        [
            "Procedimentos",
        ],
    )

    validar_colunas(
        lista_convenios_df,
        NOME_ABA_CONVENIOS,
        [
            "convenios",
        ],
    )

    validar_colunas(
        outros_valores_df,
        NOME_ABA_OUTROS_VALORES,
        [
            "descricao",
            "valor",
        ],
    )

except ValueError as error:
    st.error(
        str(error)
    )

    st.stop()


# ============================================================
# Listas para os seletores
# ============================================================

nomes_medicos = obter_lista_unica(
    lista_medicos_df,
    "nome_medico",
)

nomes_exames = obter_lista_unica(
    lista_exames_df,
    "nome_exame",
)

procedimentos_disponiveis = obter_lista_unica(
    lista_procedimentos_df,
    "Procedimentos",
)

convenios_disponiveis = obter_lista_unica(
    lista_convenios_df,
    "convenios",
)


if not nomes_medicos:
    st.warning(
        "Nenhum médico foi encontrado na aba "
        f"`{NOME_ABA_MEDICOS}`."
    )

    st.stop()


if not nomes_exames:
    st.warning(
        "Nenhum exame foi encontrado na aba "
        f"`{NOME_ABA_EXAMES}`."
    )

    st.stop()


if not procedimentos_disponiveis:
    st.warning(
        "Nenhum procedimento foi encontrado na aba "
        f"`{NOME_ABA_PROCEDIMENTOS}`."
    )

    st.stop()


if not convenios_disponiveis:
    st.warning(
        "Nenhum convênio foi encontrado na aba "
        f"`{NOME_ABA_CONVENIOS}`."
    )

    st.stop()


# ============================================================
# Taxa do aparelho
# ============================================================

(
    taxa_aparelho,
    encontrou_taxa_aparelho,
) = obter_taxa_aparelho(
    outros_valores_df
)


if not encontrou_taxa_aparelho:
    st.warning(
        "A descrição `taxa_aparelho` não foi encontrada "
        "na aba `outros_valores`. "
        "O sistema utilizará R$ 0,00."
    )


# ============================================================
# Campos para preenchimento
# ============================================================

with st.container(border=True):
    st.markdown(
        "### Dados do atendimento"
    )

    coluna_data, coluna_atendimento = st.columns(2)

    with coluna_data:
        data_atendimento = st.date_input(
            "Data do atendimento",
            value=date.today(),
            format="DD/MM/YYYY",
            key=(
                f"data_atendimento_"
                f"{versao_formulario}"
            ),
        )

    with coluna_atendimento:
        numero_atendimento = st.text_input(
            "Número do atendimento",
            placeholder=(
                "Digite o número do atendimento"
            ),
            key=(
                f"numero_atendimento_"
                f"{versao_formulario}"
            ),
        )

    coluna_paciente, coluna_convenio = st.columns(
        [2, 1]
    )

    with coluna_paciente:
        nome_paciente = st.text_input(
            "Nome do paciente",
            placeholder=(
                "Digite o nome completo do paciente"
            ),
            key=(
                f"nome_paciente_"
                f"{versao_formulario}"
            ),
        )

    with coluna_convenio:
        convenio_selecionado = st.selectbox(
            "Convênio",
            options=convenios_disponiveis,
            index=None,
            placeholder="Selecione um convênio",
            key=(
                f"convenio_"
                f"{versao_formulario}"
            ),
        )

    coluna_medico, coluna_exame = st.columns(2)

    with coluna_medico:
        nome_medico = st.selectbox(
            "Médico responsável",
            options=nomes_medicos,
            index=None,
            placeholder="Selecione um médico",
            key=(
                f"nome_medico_"
                f"{versao_formulario}"
            ),
        )

    with coluna_exame:
        nome_exame = st.selectbox(
            "Exame realizado",
            options=nomes_exames,
            index=None,
            placeholder="Selecione um exame",
            key=(
                f"nome_exame_"
                f"{versao_formulario}"
            ),
        )

    procedimentos_selecionados = st.multiselect(
        "Procedimentos realizados",
        options=procedimentos_disponiveis,
        default=None,
        placeholder=(
            "Selecione um ou mais procedimentos"
        ),
        key=(
            f"procedimentos_"
            f"{versao_formulario}"
        ),
    )


procedimentos_formatados = formatar_procedimentos(
    procedimentos_selecionados
)


# ============================================================
# Valores do exame selecionado
# ============================================================

valor_exame = 0.0
valor_medico = 0.0
exame_encontrado = False


if nome_exame:
    exame_selecionado_df = lista_exames_df.loc[
        lista_exames_df["nome_exame"]
        .astype(str)
        .str.strip()
        .eq(nome_exame)
    ]

    if not exame_selecionado_df.empty:
        exame_selecionado = (
            exame_selecionado_df.iloc[0]
        )

        valor_exame = converter_para_float(
            exame_selecionado["valor_exame"]
        )

        valor_medico = converter_para_float(
            exame_selecionado["valor_medico"]
        )

        exame_encontrado = True


# ============================================================
# Resumo do registro
# ============================================================

campos_principais_preenchidos = all(
    [
        numero_atendimento.strip(),
        nome_paciente.strip(),
        convenio_selecionado,
        nome_medico,
        nome_exame,
        procedimentos_selecionados,
        exame_encontrado,
    ]
)


with st.container(border=True):
    st.markdown(
        "### Conferência do atendimento"
    )

    if not campos_principais_preenchidos:
        st.info(
            "Preencha os campos acima para visualizar "
            "o resumo completo do atendimento."
        )

    else:
        coluna_resumo_1, coluna_resumo_2 = (
            st.columns(2)
        )

        with coluna_resumo_1:
            st.markdown(
                f"**Data:** "
                f"{data_atendimento.strftime('%d/%m/%Y')}"
            )

            st.markdown(
                f"**Número do atendimento:** "
                f"{numero_atendimento.strip()}"
            )

            st.markdown(
                f"**Paciente:** "
                f"{nome_paciente.strip()}"
            )

            st.markdown(
                f"**Convênio:** "
                f"{convenio_selecionado}"
            )

        with coluna_resumo_2:
            st.markdown(
                f"**Médico:** "
                f"{nome_medico}"
            )

            st.markdown(
                f"**Exame:** "
                f"{nome_exame}"
            )

            st.markdown(
                f"**Procedimentos:** "
                f"{procedimentos_formatados}"
            )

        st.divider()

        (
            coluna_valor_exame,
            coluna_valor_medico,
            coluna_taxa,
        ) = st.columns(3)

        with coluna_valor_exame:
            st.metric(
                "Valor do exame",
                formatar_moeda(
                    valor_exame
                ),
            )

        with coluna_valor_medico:
            st.metric(
                "Valor recebido pelo médico",
                formatar_moeda(
                    valor_medico
                ),
            )

        with coluna_taxa:
            st.metric(
                "Taxa do aparelho",
                formatar_moeda(
                    taxa_aparelho
                ),
            )


# ============================================================
# Salvar registro
# ============================================================

dados_validos = all(
    [
        numero_atendimento.strip(),
        nome_paciente.strip(),
        convenio_selecionado,
        nome_medico,
        nome_exame,
        procedimentos_selecionados,
        exame_encontrado,
    ]
)


salvar_dados = st.button(
    "💾 Salvar atendimento",
    type="primary",
    use_container_width=True,
    disabled=not dados_validos,
)


if salvar_dados:
    numero_atendimento_limpo = (
        numero_atendimento.strip()
    )

    nome_paciente_limpo = (
        nome_paciente.strip()
    )

    procedimentos_formatados = (
        formatar_procedimentos(
            procedimentos_selecionados
        )
    )

    # Ordem das colunas da aba base_dados:
    #
    # data
    # numero_atendimento
    # nome_paciente
    # convenio
    # nome_medico
    # nome_exame
    # procedimentos
    # valor_exame
    # taxa_aparelho
    # valor_medico

    nova_linha = [
        data_atendimento.strftime(
            "%d/%m/%Y"
        ),
        numero_atendimento_limpo,
        nome_paciente_limpo,
        convenio_selecionado,
        nome_medico,
        nome_exame,
        procedimentos_formatados,
        valor_exame,
        taxa_aparelho,
        valor_medico,
    ]

    try:
        with st.spinner(
            "Salvando atendimento..."
        ):
            append_sheet_data(
                NOME_ABA_BASE_DADOS,
                [nova_linha],
            )

        st.session_state[
            "mensagem_sucesso_atendimento"
        ] = (
            f"Atendimento "
            f"{numero_atendimento_limpo} de "
            f"{nome_paciente_limpo} salvo com sucesso."
        )

        st.session_state[
            "versao_formulario_atendimento"
        ] += 1

        st.toast(
            "Dados salvos com sucesso!",
            icon="😍",
        )

        st.rerun()

    except Exception as error:
        st.error(
            "Não foi possível salvar o atendimento "
            "na planilha."
        )

        st.exception(error)
