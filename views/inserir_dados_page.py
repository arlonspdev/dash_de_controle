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
NOME_ABA_OUTROS_VALORES = "outros_valores"
NOME_ABA_BASE_DADOS = "base_dados"


# ============================================================
# Funções auxiliares
# ============================================================

def formatar_moeda(valor: float) -> str:
    """
    Formata um número no padrão brasileiro.
    Exemplo: 1234.5 -> R$ 1.234,50
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

    texto = re.sub(r"[R$\s]", "", texto)

    # Exemplo brasileiro: 1.234,56
    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "")
            texto = texto.replace(",", ".")
        else:
            # Exemplo internacional: 1,234.56
            texto = texto.replace(",", "")

    elif "," in texto:
        texto = texto.replace(".", "")
        texto = texto.replace(",", ".")

    try:
        return float(texto)

    except ValueError as error:
        raise ValueError(
            f"Não foi possível converter o valor '{valor}' para número."
        ) from error


def normalizar_texto(valor: str) -> str:
    """
    Remove acentos, espaços extras e diferenças entre
    hífen, underline e espaço.
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
    Retorna os valores preenchidos e únicos de uma coluna,
    preservando a ordem da planilha.
    """
    valores = (
        dataframe[nome_coluna]
        .dropna()
        .astype(str)
        .str.strip()
    )

    valores = valores[valores.ne("")]

    return valores.drop_duplicates().tolist()


def obter_outro_valor(
    dataframe: pd.DataFrame,
    descricoes_possiveis: list[str],
) -> tuple[float, bool]:
    """
    Procura uma descrição na aba outros_valores.

    Retorna:
        valor encontrado;
        indicador informando se a descrição foi encontrada.
    """
    if dataframe.empty:
        return 0.0, False

    descricoes_normalizadas = {
        normalizar_texto(descricao)
        for descricao in descricoes_possiveis
    }

    base = dataframe.copy()

    base["descricao_normalizada"] = (
        base["descricao"]
        .fillna("")
        .apply(normalizar_texto)
    )

    resultado = base.loc[
        base["descricao_normalizada"].isin(descricoes_normalizadas)
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
    st.session_state["versao_formulario_atendimento"] = 0


mensagem_sucesso = st.session_state.pop(
    "mensagem_sucesso_atendimento",
    None,
)

if mensagem_sucesso:
    st.success(mensagem_sucesso)


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
        st.title("ARLONSP - SERVIÇOS MÉDICOS")
        st.caption(
            "Registro de atendimentos e utilização do equipamento"
        )


coluna_descricao, coluna_atualizar = st.columns(
    [5, 1],
    vertical_alignment="center",
)

with coluna_descricao:
    st.subheader("Inserir novo atendimento")

with coluna_atualizar:
    atualizar_listas = st.button(
        "🔄 Atualizar listas",
        use_container_width=True,
    )

if atualizar_listas:
    get_sheet_data.clear()
    st.rerun()


# ============================================================
# Carregamento das planilhas
# ============================================================

try:
    with st.spinner("Carregando médicos e exames..."):
        lista_exames_df = get_sheet_data(
            NOME_ABA_EXAMES
        ).copy()

        lista_medicos_df = get_sheet_data(
            NOME_ABA_MEDICOS
        ).copy()

        outros_valores_df = get_sheet_data(
            NOME_ABA_OUTROS_VALORES
        ).copy()

except Exception as error:
    st.error("Não foi possível carregar os dados das planilhas.")
    st.exception(error)
    st.stop()


# Remove espaços acidentais nos nomes das colunas.
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

outros_valores_df.columns = (
    outros_valores_df.columns
    .astype(str)
    .str.strip()
)


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
        outros_valores_df,
        NOME_ABA_OUTROS_VALORES,
        [
            "descricao",
            "valor",
        ],
    )

except ValueError as error:
    st.error(str(error))
    st.stop()


nomes_medicos = obter_lista_unica(
    lista_medicos_df,
    "nome_medico",
)

nomes_exames = obter_lista_unica(
    lista_exames_df,
    "nome_exame",
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


# ============================================================
# Valores adicionais
# ============================================================

taxa_aparelho, encontrou_taxa_aparelho = obter_outro_valor(
    outros_valores_df,
    [
        "taxa_aparelho",
        "taxa aparelho",
        "taxa do aparelho",
    ],
)

valor_sobreaviso, encontrou_sobreaviso = obter_outro_valor(
    outros_valores_df,
    [
        "valor_sobreaviso",
        "valor sobreaviso",
        "sobreaviso",
    ],
)


# ============================================================
# Campos para preenchimento
# ============================================================

with st.container(border=True):
    st.markdown("### Dados do atendimento")

    coluna_data, coluna_atendimento = st.columns(2)

    with coluna_data:
        data_atendimento = st.date_input(
            "Data do atendimento",
            value=date.today(),
            format="DD/MM/YYYY",
            key=f"data_atendimento_{versao_formulario}",
        )

    with coluna_atendimento:
        numero_atendimento = st.text_input(
            "Número do atendimento",
            placeholder="Digite o número do atendimento",
            key=f"numero_atendimento_{versao_formulario}",
        )

    nome_paciente = st.text_input(
        "Nome do paciente",
        placeholder="Digite o nome completo do paciente",
        key=f"nome_paciente_{versao_formulario}",
    )

    coluna_medico, coluna_exame = st.columns(2)

    with coluna_medico:
        nome_medico = st.selectbox(
            "Médico responsável",
            options=nomes_medicos,
            index=None,
            placeholder="Selecione um médico",
            key=f"nome_medico_{versao_formulario}",
        )

    with coluna_exame:
        nome_exame = st.selectbox(
            "Exame realizado",
            options=nomes_exames,
            index=None,
            placeholder="Selecione um exame",
            key=f"nome_exame_{versao_formulario}",
        )


# ============================================================
# Localiza os valores do exame selecionado
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
        exame_selecionado = exame_selecionado_df.iloc[0]

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

with st.container(border=True):
    st.markdown("### Conferência do atendimento")

    campos_principais_preenchidos = all(
        [
            numero_atendimento.strip(),
            nome_paciente.strip(),
            nome_medico,
            nome_exame,
            exame_encontrado,
        ]
    )

    if not campos_principais_preenchidos:
        st.info(
            "Preencha os campos acima para visualizar o resumo "
            "completo do atendimento."
        )

    else:
        coluna_resumo_1, coluna_resumo_2 = st.columns(2)

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

        with coluna_resumo_2:
            st.markdown(
                f"**Médico:** {nome_medico}"
            )

            st.markdown(
                f"**Exame:** {nome_exame}"
            )

        st.divider()

        coluna_valor_exame, coluna_valor_medico = st.columns(2)

        with coluna_valor_exame:
            st.metric(
                "Valor do exame",
                formatar_moeda(valor_exame),
            )

        with coluna_valor_medico:
            st.metric(
                "Valor recebido pelo médico",
                formatar_moeda(valor_medico),
            )

        with st.expander("Ver outros valores do registro"):
            coluna_taxa, coluna_sobreaviso = st.columns(2)

            with coluna_taxa:
                st.metric(
                    "Taxa do aparelho",
                    formatar_moeda(taxa_aparelho),
                )

            with coluna_sobreaviso:
                st.metric(
                    "Valor de sobreaviso",
                    formatar_moeda(valor_sobreaviso),
                )


# ============================================================
# Alertas sobre outros valores
# ============================================================

if not encontrou_taxa_aparelho:
    st.warning(
        "A descrição `taxa_aparelho` não foi encontrada na aba "
        "`outros_valores`. O sistema utilizará R$ 0,00."
    )


if not encontrou_sobreaviso:
    st.warning(
        "A descrição `valor_sobreaviso` não foi encontrada na aba "
        "`outros_valores`. O sistema utilizará R$ 0,00."
    )


# ============================================================
# Salvar registro
# ============================================================

dados_validos = all(
    [
        numero_atendimento.strip(),
        nome_paciente.strip(),
        nome_medico,
        nome_exame,
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
    numero_atendimento_limpo = numero_atendimento.strip()
    nome_paciente_limpo = nome_paciente.strip()

    # A ordem precisa ser a mesma das colunas da aba base_dados:
    #
    # data
    # numero_atendimento
    # nome_paciente
    # nome_medico
    # nome_exame
    # valor_exame
    # taxa_aparelho
    # valor_medico
    # valor_sobreaviso

    nova_linha = [
        data_atendimento.strftime("%d/%m/%Y"),
        numero_atendimento_limpo,
        nome_paciente_limpo,
        nome_medico,
        nome_exame,
        valor_exame,
        taxa_aparelho,
        valor_medico,
        valor_sobreaviso,
    ]

    try:
        with st.spinner("Salvando atendimento..."):
            append_sheet_data(
                NOME_ABA_BASE_DADOS,
                [nova_linha],
            )

        st.session_state[
            "mensagem_sucesso_atendimento"
        ] = (
            f"Atendimento {numero_atendimento_limpo} "
            f"de {nome_paciente_limpo} salvo com sucesso."
        )

        # Altera as chaves dos widgets para limpar os campos.
        st.session_state[
            "versao_formulario_atendimento"
        ] += 1

        st.rerun()

    except Exception as error:
        st.error(
            "Não foi possível salvar o atendimento "
            "na planilha."
        )
        st.exception(error)