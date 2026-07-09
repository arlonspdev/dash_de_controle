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
    Converte valores numéricos e monetários para float.
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
    Retorna valores preenchidos, únicos e em ordem alfabética.

    A ordenação ignora diferenças entre letras maiúsculas,
    minúsculas e acentos.
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

    valores_unicos = (
        valores
        .drop_duplicates()
        .tolist()
    )

    return sorted(
        valores_unicos,
        key=normalizar_texto,
    )


def formatar_procedimentos(
    procedimentos_selecionados: list[str],
    incluir_apostrofo: bool = False,
) -> str:
    """
    Formata uma lista de procedimentos.

    Exibição:
        +Polipectomia +Mucosectomia

    Google Sheets:
        '+Polipectomia +Mucosectomia
    """
    procedimentos_formatados = []

    for procedimento in procedimentos_selecionados:
        procedimento_limpo = str(
            procedimento
        ).strip()

        if procedimento_limpo.startswith("'"):
            procedimento_limpo = (
                procedimento_limpo[1:].strip()
            )

        if procedimento_limpo.startswith("+"):
            procedimento_limpo = (
                procedimento_limpo[1:].strip()
            )

        if procedimento_limpo:
            procedimentos_formatados.append(
                f"+{procedimento_limpo}"
            )

    texto_formatado = " ".join(
        procedimentos_formatados
    )

    if incluir_apostrofo and texto_formatado:
        return f"'{texto_formatado}"

    return texto_formatado


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


def obter_dados_exame(
    lista_exames_df: pd.DataFrame,
    nome_exame: str | None,
) -> tuple[float, float, bool]:
    """
    Retorna o valor do exame, o valor do médico e se o
    exame foi localizado na lista.
    """
    if not nome_exame:
        return 0.0, 0.0, False

    exame_selecionado_df = lista_exames_df.loc[
        lista_exames_df["nome_exame"]
        .astype(str)
        .str.strip()
        .eq(nome_exame)
    ]

    if exame_selecionado_df.empty:
        return 0.0, 0.0, False

    exame_selecionado = (
        exame_selecionado_df.iloc[0]
    )

    valor_exame = converter_para_float(
        exame_selecionado["valor_exame"]
    )

    valor_medico = converter_para_float(
        exame_selecionado["valor_medico"]
    )

    return (
        valor_exame,
        valor_medico,
        True,
    )


def adicionar_bloco_exame() -> None:
    """
    Adiciona um novo bloco de exame e procedimentos.
    """
    st.session_state[
        "quantidade_blocos_exames"
    ] += 1


def remover_bloco_exame() -> None:
    """
    Remove o último bloco de exame e procedimentos.
    """
    quantidade_atual = st.session_state.get(
        "quantidade_blocos_exames",
        1,
    )

    if quantidade_atual > 1:
        st.session_state[
            "quantidade_blocos_exames"
        ] = quantidade_atual - 1


# ============================================================
# Estado da página
# ============================================================

if "versao_formulario_atendimento" not in st.session_state:
    st.session_state[
        "versao_formulario_atendimento"
    ] = 0


if "quantidade_blocos_exames" not in st.session_state:
    st.session_state[
        "quantidade_blocos_exames"
    ] = 1


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

quantidade_blocos_exames = st.session_state[
    "quantidade_blocos_exames"
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


# ============================================================
# Limpeza dos nomes das colunas
# ============================================================

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
# Listas dos seletores
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


# Procedimentos são opcionais. A página continua funcionando
# mesmo que a lista de procedimentos esteja vazia.
if not procedimentos_disponiveis:
    st.warning(
        "Nenhum procedimento foi encontrado na aba "
        f"`{NOME_ABA_PROCEDIMENTOS}`. "
        "O atendimento poderá ser salvo sem procedimento."
    )


# Convênios são opcionais. A página continua funcionando
# mesmo que a lista de convênios esteja vazia.
if not convenios_disponiveis:
    st.warning(
        "Nenhum convênio foi encontrado na aba "
        f"`{NOME_ABA_CONVENIOS}`. "
        "O atendimento poderá ser salvo sem convênio."
    )


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
# Dados comuns do atendimento
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

    coluna_medico, coluna_convenio = st.columns(2)

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

    with coluna_convenio:
        convenio_selecionado = st.selectbox(
            "Convênio — opcional",
            options=convenios_disponiveis,
            index=None,
            placeholder=(
                "Selecione um convênio, se houver"
            ),
            key=(
                f"convenio_"
                f"{versao_formulario}"
            ),
        )


# ============================================================
# Exames e procedimentos
# ============================================================

st.markdown(
    "### Exames e procedimentos"
)

st.caption(
    "Selecione o exame realizado. O preenchimento dos "
    "procedimentos é opcional. Use o botão abaixo para "
    "adicionar outros exames ao mesmo atendimento."
)


itens_exames = []


for indice in range(
    quantidade_blocos_exames
):
    with st.container(border=True):
        st.markdown(
            f"#### Exame {indice + 1}"
        )

        coluna_exame, coluna_procedimentos = (
            st.columns([1, 2])
        )

        with coluna_exame:
            nome_exame = st.selectbox(
                "Exame realizado",
                options=nomes_exames,
                index=None,
                placeholder="Selecione um exame",
                key=(
                    f"nome_exame_"
                    f"{versao_formulario}_"
                    f"{indice}"
                ),
            )

        with coluna_procedimentos:
            procedimentos_selecionados = (
                st.multiselect(
                    "Procedimentos — opcional",
                    options=procedimentos_disponiveis,
                    default=[],
                    placeholder=(
                        "Selecione os procedimentos, "
                        "se houver"
                    ),
                    key=(
                        f"procedimentos_"
                        f"{versao_formulario}_"
                        f"{indice}"
                    ),
                )
            )

        (
            valor_exame,
            valor_medico,
            exame_encontrado,
        ) = obter_dados_exame(
            lista_exames_df,
            nome_exame,
        )

        itens_exames.append(
            {
                "indice": indice,
                "nome_exame": nome_exame,
                "procedimentos": (
                    procedimentos_selecionados
                ),
                "valor_exame": valor_exame,
                "valor_medico": valor_medico,
                "exame_encontrado": (
                    exame_encontrado
                ),
            }
        )


coluna_adicionar, coluna_remover = st.columns(2)

with coluna_adicionar:
    st.button(
        "➕ Adicionar outro exame",
        type="secondary",
        use_container_width=True,
        on_click=adicionar_bloco_exame,
    )

with coluna_remover:
    st.button(
        "➖ Remover último exame",
        type="secondary",
        use_container_width=True,
        disabled=(
            quantidade_blocos_exames <= 1
        ),
        on_click=remover_bloco_exame,
    )


# ============================================================
# Validação dos exames
# ============================================================

nomes_exames_preenchidos = [
    item["nome_exame"]
    for item in itens_exames
    if item["nome_exame"]
]


nomes_exames_normalizados = [
    normalizar_texto(nome_exame)
    for nome_exame in nomes_exames_preenchidos
]


possui_exames_duplicados = (
    len(nomes_exames_normalizados)
    != len(set(nomes_exames_normalizados))
)


if possui_exames_duplicados:
    st.warning(
        "O mesmo exame foi selecionado mais de uma vez. "
        "Utilize somente um bloco para cada exame."
    )


# Apenas o exame é obrigatório em cada bloco.
# Procedimentos podem ficar vazios.
itens_exames_validos = (
    bool(itens_exames)
    and all(
        [
            item["nome_exame"]
            and item["exame_encontrado"]
            for item in itens_exames
        ]
    )
    and not possui_exames_duplicados
)


campos_comuns_validos = all(
    [
        numero_atendimento.strip(),
        nome_paciente.strip(),
        nome_medico,
    ]
)


dados_validos = (
    campos_comuns_validos
    and itens_exames_validos
)


# ============================================================
# Conferência do atendimento
# ============================================================

with st.container(border=True):
    st.markdown(
        "### Conferência do atendimento"
    )

    if not dados_validos:
        mensagens_pendentes = []

        if not numero_atendimento.strip():
            mensagens_pendentes.append(
                "número do atendimento"
            )

        if not nome_paciente.strip():
            mensagens_pendentes.append(
                "nome do paciente"
            )

        if not nome_medico:
            mensagens_pendentes.append(
                "médico responsável"
            )

        if not itens_exames_validos:
            mensagens_pendentes.append(
                "exames"
            )

        st.info(
            "Preencha corretamente: "
            + ", ".join(mensagens_pendentes)
            + "."
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

        with coluna_resumo_2:
            st.markdown(
                f"**Médico:** {nome_medico}"
            )

            st.markdown(
                f"**Convênio:** "
                f"{convenio_selecionado or 'Não informado'}"
            )

            st.markdown(
                f"**Quantidade de exames:** "
                f"{len(itens_exames)}"
            )

        st.divider()

        resumo_exames = []

        for item in itens_exames:
            procedimentos_exibicao = (
                formatar_procedimentos(
                    item["procedimentos"],
                    incluir_apostrofo=False,
                )
            )

            resumo_exames.append(
                {
                    "Exame": item["nome_exame"],
                    "Procedimentos": (
                        procedimentos_exibicao
                        or "Não informado"
                    ),
                    "Valor do exame": (
                        item["valor_exame"]
                    ),
                    "Valor médico": (
                        item["valor_medico"]
                    ),
                    "Taxa do aparelho": (
                        taxa_aparelho
                    ),
                }
            )

        resumo_exames_df = pd.DataFrame(
            resumo_exames
        )

        st.dataframe(
            resumo_exames_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Exame": (
                    st.column_config.TextColumn(
                        "Exame",
                        width="medium",
                    )
                ),
                "Procedimentos": (
                    st.column_config.TextColumn(
                        "Procedimentos",
                        width="large",
                    )
                ),
                "Valor do exame": (
                    st.column_config.NumberColumn(
                        "Valor do exame",
                        format="R$ %.2f",
                    )
                ),
                "Valor médico": (
                    st.column_config.NumberColumn(
                        "Valor médico",
                        format="R$ %.2f",
                    )
                ),
                "Taxa do aparelho": (
                    st.column_config.NumberColumn(
                        "Taxa do aparelho",
                        format="R$ %.2f",
                    )
                ),
            },
        )

        total_valor_exames = sum(
            item["valor_exame"]
            for item in itens_exames
        )

        total_valor_medicos = sum(
            item["valor_medico"]
            for item in itens_exames
        )

        total_taxa_aparelho = (
            taxa_aparelho
            * len(itens_exames)
        )

        quantidade_exames = len(
            itens_exames
        )

        (
            coluna_total_exames,
            coluna_quantidade_exames,
            coluna_total_medico,
            coluna_total_taxa,
        ) = st.columns(4)

        with coluna_total_exames:
            st.metric(
                "Total dos exames",
                formatar_moeda(
                    total_valor_exames
                ),
            )

        with coluna_quantidade_exames:
            st.metric(
                "Exames",
                quantidade_exames,
            )

        with coluna_total_medico:
            st.metric(
                "Total do médico",
                formatar_moeda(
                    total_valor_medicos
                ),
            )

        with coluna_total_taxa:
            st.metric(
                "Taxa do aparelho",
                formatar_moeda(
                    total_taxa_aparelho
                ),
            )

        st.caption(
            "Para exames com procedimentos, será criada uma "
            "linha para cada procedimento. Para exames sem "
            "procedimentos, será criada uma linha com a coluna "
            "`procedimentos` vazia. Os valores financeiros são "
            "registrados apenas na primeira linha de cada exame."
        )


# ============================================================
# Salvar registro
# ============================================================

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

    convenio_para_salvar = (
        convenio_selecionado or ""
    )

    novas_linhas = []


    for item in itens_exames:
        # Quando não houver procedimento, cria uma única
        # linha para o exame com a coluna vazia.
        procedimentos_do_exame = (
            item["procedimentos"]
            if item["procedimentos"]
            else [None]
        )

        for indice_procedimento, procedimento in enumerate(
            procedimentos_do_exame
        ):
            primeira_linha_do_exame = (
                indice_procedimento == 0
            )

            if procedimento is None:
                procedimento_para_salvar = ""

            else:
                procedimento_para_salvar = (
                    formatar_procedimentos(
                        [procedimento],
                        incluir_apostrofo=True,
                    )
                )

            # Os valores financeiros são incluídos somente
            # na primeira linha de cada exame.
            #
            # Isso evita que os valores sejam duplicados
            # quando um exame possui vários procedimentos.

            valor_exame_linha = (
                item["valor_exame"]
                if primeira_linha_do_exame
                else 0.0
            )

            taxa_aparelho_linha = (
                taxa_aparelho
                if primeira_linha_do_exame
                else 0.0
            )

            valor_medico_linha = (
                item["valor_medico"]
                if primeira_linha_do_exame
                else 0.0
            )

            nova_linha = [
                data_atendimento.strftime(
                    "%d/%m/%Y"
                ),
                numero_atendimento_limpo,
                nome_paciente_limpo,
                convenio_para_salvar,
                nome_medico,
                item["nome_exame"],
                procedimento_para_salvar,
                valor_exame_linha,
                taxa_aparelho_linha,
                valor_medico_linha,
            ]

            novas_linhas.append(
                nova_linha
            )


    try:
        with st.spinner(
            "Salvando atendimento..."
        ):
            append_sheet_data(
                NOME_ABA_BASE_DADOS,
                novas_linhas,
            )

        quantidade_linhas = len(
            novas_linhas
        )

        st.session_state[
            "mensagem_sucesso_atendimento"
        ] = (
            f"Atendimento "
            f"{numero_atendimento_limpo} de "
            f"{nome_paciente_limpo} salvo com sucesso. "
            f"{quantidade_linhas} registro(s) foram "
            "adicionados à base."
        )

        st.session_state[
            "versao_formulario_atendimento"
        ] += 1

        st.session_state[
            "quantidade_blocos_exames"
        ] = 1

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