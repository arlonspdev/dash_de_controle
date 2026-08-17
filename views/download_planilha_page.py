from calendar import monthrange
from datetime import date
from html import escape
from io import BytesIO
import re
import unicodedata

import pandas as pd
import streamlit as st

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from auxiliar.google_sheets import (
    get_sheet_data,
    set_sheet_data,
)


NOME_ABA_BASE_DADOS = "base_dados"
NOME_ABA_MEDICOS = "lista_medicos"
NOME_ABA_EXAMES = "lista_exames"
NOME_ABA_CONVENIOS = "lista_convenios"
NOME_ABA_PROCEDIMENTOS = "lista_procedimentos"

NOME_EMPRESA = "ARLONSP - SERVIÇOS MÉDICOS"


COLUNAS_ORIGINAIS = [
    "data",
    "numero_atendimento",
    "nome_paciente",
    "convenio",
    "nome_medico",
    "nome_exame",
    "procedimentos",
    "valor_exame",
    "taxa_aparelho",
    "valor_medico",
]


# Ordem das colunas editáveis da aba base_dados.
COLUNAS_BASE_DADOS_EDITAVEL = [
    "data",
    "numero_atendimento",
    "nome_paciente",
    "convenio",
    "nome_medico",
    "nome_exame",
    "procedimentos",
    "valor_exame",
    "taxa_aparelho",
    "valor_medico",
    "medico_auxiliar",
    "valor_auxilio",
]


COLUNAS_BONITAS_EDITOR = {
    "data": "Data",
    "numero_atendimento": "Número do atendimento",
    "nome_paciente": "Paciente",
    "convenio": "Convênio",
    "nome_medico": "Médico",
    "nome_exame": "Exame",
    "procedimentos": "Procedimentos",
    "valor_exame": "Valor do exame",
    "taxa_aparelho": "Taxa do aparelho",
    "valor_medico": "Valor médico",
    "medico_auxiliar": "Médico auxiliar",
    "valor_auxilio": "Valor auxílio",
}

COLUNAS_BONITAS_EDITOR_INVERSO = {
    valor: chave
    for chave, valor in COLUNAS_BONITAS_EDITOR.items()
}


COLUNAS_BONITAS = {
    "data_convertida": "Data",
    "numero_atendimento": "Número do atendimento",
    "nome_paciente": "Paciente",
    "convenio": "Convênio",
    "nome_medico": "Médico",
    "nome_exame": "Exame",
    "procedimentos": "Procedimentos",
    "valor_exame": "Valor do exame",
    "taxa_aparelho": "Taxa do aparelho",
}


COLUNAS_TABELA = [
    "Data",
    "Número do atendimento",
    "Paciente",
    "Convênio",
    "Médico",
    "Exame",
    "Procedimentos",
    "Valor do exame",
    "Taxa do aparelho",
]


COLUNAS_MONETARIAS = [
    "Valor do exame",
    "Taxa do aparelho",
]


# ============================================================
# Funções auxiliares
# ============================================================

def formatar_moeda(valor: float) -> str:
    """
    Formata um valor como moeda brasileira.
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

    Aceita:
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
            texto = texto.replace(".", "")
            texto = texto.replace(",", ".")

        else:
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
    Converte datas da planilha para datetime.
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


def normalizar_texto(valor: str) -> str:
    """
    Remove acentos e trata underline, hífen e espaços
    como equivalentes. Usada para ordenar listas de opções.
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


def obter_lista_unica(
    dataframe: pd.DataFrame,
    nome_coluna: str,
) -> list[str]:
    """
    Retorna valores preenchidos, únicos e em ordem alfabética.
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


def montar_opcoes_selecao(
    *series: pd.Series,
    lista_cadastrada: list[str],
) -> list[str]:
    """
    Une a lista cadastrada com quaisquer valores já existentes
    na base, para que registros antigos não fiquem "fora" das
    opções do seletor.
    """
    valores_existentes: set[str] = set()

    for serie in series:
        valores = (
            serie
            .dropna()
            .astype(str)
            .str.strip()
        )

        valores_existentes.update(
            valores.loc[valores.ne("")].tolist()
        )

    todas_opcoes = set(lista_cadastrada) | valores_existentes

    return sorted(
        todas_opcoes,
        key=normalizar_texto,
    )


def converter_valor_para_edicao(valor) -> float:
    """
    Converte um valor monetário para float sem levantar erro.

    Usado no editor: valores inválidos viram 0.0 em vez de
    bloquear a abertura da tabela para edição.
    """
    try:
        return converter_para_float(valor)

    except (TypeError, ValueError):
        return 0.0


def normalizar_procedimentos(valor) -> str:
    """
    Normaliza o texto de procedimentos.

    Remove o apóstrofo inicial usado no formato antigo para
    proteger o Google Sheets e converte a antiga separação por
    "+" para o separador atual ";". Já está preparada para
    textos que já usam ";" (não altera nesse caso).
    """
    texto = str(valor or "").strip()

    if texto.startswith("'"):
        texto = texto[1:].strip()

    if not texto:
        return ""

    itens = [
        item.strip()
        for item in re.split(r"[+;]", texto)
        if item.strip()
    ]

    return "; ".join(itens)


@st.dialog(
    "Editar dados",
    width="large",
)
def abrir_dialogo_editar_base_dados() -> None:
    """
    Permite editar diretamente todos os registros da aba
    base_dados, com campos inteligentes (data, listas de
    seleção e lista de procedimentos) para reduzir erros
    de digitação.
    """
    st.caption(
        "Edite os dados diretamente. Convênio, médico, exame "
        "e procedimentos usam listas para evitar erros de "
        "digitação. Ao salvar, toda a aba `base_dados` será "
        "substituída pelos dados exibidos abaixo."
    )

    try:
        with st.spinner(
            "Carregando dados para edição..."
        ):
            base_dados_bruta_df = get_sheet_data(
                NOME_ABA_BASE_DADOS
            ).copy()

            lista_medicos_df = get_sheet_data(
                NOME_ABA_MEDICOS
            ).copy()

            lista_exames_df = get_sheet_data(
                NOME_ABA_EXAMES
            ).copy()

            lista_convenios_df = get_sheet_data(
                NOME_ABA_CONVENIOS
            ).copy()

            lista_procedimentos_df = get_sheet_data(
                NOME_ABA_PROCEDIMENTOS
            ).copy()

    except Exception as error:
        st.error(
            "Não foi possível carregar os dados para edição."
        )

        st.exception(error)
        return

    base_dados_bruta_df.columns = (
        base_dados_bruta_df.columns
        .astype(str)
        .str.strip()
    )

    for coluna in COLUNAS_BASE_DADOS_EDITAVEL:
        if coluna not in base_dados_bruta_df.columns:
            base_dados_bruta_df[coluna] = ""

    tabela_editor_df = (
        base_dados_bruta_df[
            COLUNAS_BASE_DADOS_EDITAVEL
        ]
        .copy()
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # Opções das listas de seleção
    # --------------------------------------------------------

    convenios_disponiveis = (
        obter_lista_unica(
            lista_convenios_df,
            "convenios",
        )
        if "convenios" in lista_convenios_df.columns
        else []
    )

    nomes_medicos = (
        obter_lista_unica(
            lista_medicos_df,
            "nome_medico",
        )
        if "nome_medico" in lista_medicos_df.columns
        else []
    )

    nomes_exames = (
        obter_lista_unica(
            lista_exames_df,
            "nome_exame",
        )
        if "nome_exame" in lista_exames_df.columns
        else []
    )

    opcoes_convenio = montar_opcoes_selecao(
        tabela_editor_df["convenio"],
        lista_cadastrada=convenios_disponiveis,
    )

    opcoes_medico = montar_opcoes_selecao(
        tabela_editor_df["nome_medico"],
        tabela_editor_df["medico_auxiliar"],
        lista_cadastrada=nomes_medicos,
    )

    opcoes_exame = montar_opcoes_selecao(
        tabela_editor_df["nome_exame"],
        lista_cadastrada=nomes_exames,
    )

    procedimentos_disponiveis = (
        obter_lista_unica(
            lista_procedimentos_df,
            "Procedimentos",
        )
        if "Procedimentos" in lista_procedimentos_df.columns
        else []
    )

    if procedimentos_disponiveis:
        st.caption(
            "Procedimentos cadastrados: "
            + ", ".join(procedimentos_disponiveis)
        )

    # --------------------------------------------------------
    # Tratamento dos tipos para o editor
    # --------------------------------------------------------

    tabela_editor_df["data"] = (
        converter_coluna_data(
            tabela_editor_df["data"]
        )
        .dt.date
    )

    for coluna in [
        "valor_exame",
        "taxa_aparelho",
        "valor_medico",
        "valor_auxilio",
    ]:
        tabela_editor_df[coluna] = (
            tabela_editor_df[coluna]
            .apply(converter_valor_para_edicao)
        )

    for coluna in [
        "numero_atendimento",
        "nome_paciente",
        "convenio",
        "nome_medico",
        "nome_exame",
        "medico_auxiliar",
    ]:
        tabela_editor_df[coluna] = (
            tabela_editor_df[coluna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    # Células vazias aparecem como "não selecionado" em vez de
    # uma opção inválida na lista de seleção.
    for coluna in [
        "convenio",
        "nome_medico",
        "nome_exame",
        "medico_auxiliar",
    ]:
        tabela_editor_df[coluna] = (
            tabela_editor_df[coluna]
            .replace(
                "",
                None,
            )
        )

    tabela_editor_df["procedimentos"] = (
        tabela_editor_df["procedimentos"]
        .fillna("")
        .apply(normalizar_procedimentos)
        .apply(
            lambda texto: [
                item.strip()
                for item in texto.split(";")
                if item.strip()
            ]
        )
    )

    # --------------------------------------------------------
    # Editor
    # --------------------------------------------------------

    tabela_exibicao_editor_df = tabela_editor_df.rename(
        columns=COLUNAS_BONITAS_EDITOR
    )

    tabela_editada_df = st.data_editor(
        tabela_exibicao_editor_df,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "Data": st.column_config.DateColumn(
                "Data",
                format="DD/MM/YYYY",
                required=True,
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
            "Convênio": st.column_config.SelectboxColumn(
                "Convênio",
                options=opcoes_convenio,
                width="medium",
            ),
            "Médico": st.column_config.SelectboxColumn(
                "Médico",
                options=opcoes_medico,
                width="medium",
            ),
            "Exame": st.column_config.SelectboxColumn(
                "Exame",
                options=opcoes_exame,
                width="medium",
            ),
            "Procedimentos": st.column_config.ListColumn(
                "Procedimentos",
                help=(
                    "Adicione um ou mais procedimentos. "
                    "Pressione Enter após cada um."
                ),
                width="large",
            ),
            "Valor do exame": (
                st.column_config.NumberColumn(
                    "Valor do exame",
                    format="R$ %.2f",
                    step=0.01,
                )
            ),
            "Taxa do aparelho": (
                st.column_config.NumberColumn(
                    "Taxa do aparelho",
                    format="R$ %.2f",
                    step=0.01,
                )
            ),
            "Valor médico": (
                st.column_config.NumberColumn(
                    "Valor médico",
                    format="R$ %.2f",
                    step=0.01,
                )
            ),
            "Médico auxiliar": (
                st.column_config.SelectboxColumn(
                    "Médico auxiliar",
                    options=opcoes_medico,
                    width="medium",
                )
            ),
            "Valor auxílio": (
                st.column_config.NumberColumn(
                    "Valor auxílio",
                    format="R$ %.2f",
                    step=0.01,
                )
            ),
        },
        key="editor_base_dados_completa",
    )

    st.warning(
        "Ao salvar, todo o conteúdo da aba `base_dados` será "
        "substituído pelos dados exibidos acima."
    )

    salvar_clicado = st.button(
        "💾 Salvar alterações",
        type="primary",
        use_container_width=True,
    )

    if not salvar_clicado:
        return

    tabela_para_salvar_df = (
        tabela_editada_df
        .rename(columns=COLUNAS_BONITAS_EDITOR_INVERSO)
        .copy()
    )

    tabela_para_salvar_df["data"] = (
        tabela_para_salvar_df["data"]
        .apply(
            lambda valor: (
                valor.strftime("%d/%m/%Y")
                if hasattr(valor, "strftime")
                else str(valor or "")
            )
        )
    )

    tabela_para_salvar_df["procedimentos"] = (
        tabela_para_salvar_df["procedimentos"]
        .apply(
            lambda itens: "; ".join(
                str(item).strip()
                for item in (itens or [])
                if str(item).strip()
            )
            if isinstance(itens, list)
            else normalizar_procedimentos(itens)
        )
    )

    for coluna in [
        "numero_atendimento",
        "nome_paciente",
        "convenio",
        "nome_medico",
        "nome_exame",
        "medico_auxiliar",
    ]:
        tabela_para_salvar_df[coluna] = (
            tabela_para_salvar_df[coluna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    for coluna in [
        "valor_exame",
        "taxa_aparelho",
        "valor_medico",
        "valor_auxilio",
    ]:
        tabela_para_salvar_df[coluna] = (
            tabela_para_salvar_df[coluna]
            .apply(converter_valor_para_edicao)
        )

    tabela_para_salvar_df = tabela_para_salvar_df[
        COLUNAS_BASE_DADOS_EDITAVEL
    ]

    try:
        with st.spinner(
            "Salvando alterações..."
        ):
            set_sheet_data(
                NOME_ABA_BASE_DADOS,
                tabela_para_salvar_df,
            )

        st.session_state[
            "mensagem_base_dados_salva"
        ] = (
            "Os dados da base de atendimentos foram "
            "salvos com sucesso."
        )

        st.rerun()

    except Exception as error:
        st.error(
            "Não foi possível salvar as alterações "
            "na base de atendimentos."
        )

        st.exception(error)


def preparar_tabela_relatorio(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Prepara a tabela com nomes bonitos para exibição e PDF.
    """
    tabela = dataframe[
        [
            "data_convertida",
            "numero_atendimento",
            "nome_paciente",
            "convenio",
            "nome_medico",
            "nome_exame",
            "procedimentos",
            "valor_exame",
            "taxa_aparelho",
        ]
    ].copy()

    tabela["procedimentos"] = (
        tabela["procedimentos"]
        .fillna("")
        .apply(normalizar_procedimentos)
    )

    for coluna in [
        "numero_atendimento",
        "nome_paciente",
        "convenio",
        "nome_medico",
        "nome_exame",
    ]:
        tabela[coluna] = (
            tabela[coluna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    tabela = tabela.rename(
        columns=COLUNAS_BONITAS
    )

    tabela["Data"] = (
        tabela["Data"]
        .dt.date
    )

    return tabela[COLUNAS_TABELA]


def criar_paragrafo(
    texto,
    estilo: ParagraphStyle,
) -> Paragraph:
    """
    Cria um parágrafo seguro para o ReportLab.
    """
    texto_seguro = escape(
        str(texto or "")
    )

    texto_seguro = texto_seguro.replace(
        "\n",
        "<br/>",
    )

    return Paragraph(
        texto_seguro,
        estilo,
    )


def gerar_pdf_relatorio(
    tabela_df: pd.DataFrame,
    data_inicial: date,
    data_final: date,
) -> bytes:
    """
    Gera um PDF em memória com cabeçalho e tabela.
    """
    buffer = BytesIO()

    pagina = landscape(
        A4
    )

    documento = SimpleDocTemplate(
        buffer,
        pagesize=pagina,
        rightMargin=0.7 * cm,
        leftMargin=0.7 * cm,
        topMargin=0.7 * cm,
        bottomMargin=0.7 * cm,
        title="Relatório de atendimentos",
    )

    estilo_titulo = ParagraphStyle(
        "Titulo",
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        alignment=TA_CENTER,
        spaceAfter=4,
    )

    estilo_subtitulo = ParagraphStyle(
        "Subtitulo",
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        spaceAfter=10,
    )

    estilo_cabecalho_tabela = ParagraphStyle(
        "CabecalhoTabela",
        fontName="Helvetica-Bold",
        fontSize=6.5,
        leading=8,
        alignment=TA_CENTER,
        textColor=colors.white,
    )

    estilo_texto = ParagraphStyle(
        "TextoTabela",
        fontName="Helvetica",
        fontSize=6.3,
        leading=7.5,
        alignment=TA_LEFT,
    )

    estilo_numero = ParagraphStyle(
        "NumeroTabela",
        fontName="Helvetica",
        fontSize=6.3,
        leading=7.5,
        alignment=TA_RIGHT,
    )

    estilo_total_texto = ParagraphStyle(
        "TotalTexto",
        fontName="Helvetica-Bold",
        fontSize=6.5,
        leading=7.8,
        alignment=TA_LEFT,
    )

    estilo_total_numero = ParagraphStyle(
        "TotalNumero",
        fontName="Helvetica-Bold",
        fontSize=6.5,
        leading=7.8,
        alignment=TA_RIGHT,
    )

    elementos = []

    periodo_texto = (
        f"Período: {data_inicial.strftime('%d/%m/%Y')} "
        f"a {data_final.strftime('%d/%m/%Y')}"
    )

    elementos.append(
        Paragraph(
            NOME_EMPRESA,
            estilo_titulo,
        )
    )

    elementos.append(
        Paragraph(
            "Relatório de atendimentos",
            estilo_subtitulo,
        )
    )

    elementos.append(
        Paragraph(
            periodo_texto,
            estilo_subtitulo,
        )
    )

    elementos.append(
        Spacer(
            1,
            0.2 * cm,
        )
    )

    cabecalho = [
        criar_paragrafo(
            coluna,
            estilo_cabecalho_tabela,
        )
        for coluna in COLUNAS_TABELA
    ]

    dados_tabela = [
        cabecalho
    ]

    for _, linha in tabela_df.iterrows():
        data_formatada = (
            linha["Data"].strftime("%d/%m/%Y")
            if hasattr(linha["Data"], "strftime")
            else str(linha["Data"])
        )

        linha_pdf = []

        for coluna in COLUNAS_TABELA:
            if coluna == "Data":
                valor = data_formatada
                estilo = estilo_texto

            elif coluna in COLUNAS_MONETARIAS:
                valor = formatar_moeda(
                    linha[coluna]
                )
                estilo = estilo_numero

            else:
                valor = linha[coluna]
                estilo = estilo_texto

            linha_pdf.append(
                criar_paragrafo(
                    valor,
                    estilo,
                )
            )

        dados_tabela.append(
            linha_pdf
        )

    linha_total = []

    for indice_coluna, coluna in enumerate(
        COLUNAS_TABELA
    ):
        if indice_coluna == 0:
            valor_total = "Total"
            estilo_total = estilo_total_texto

        elif coluna in COLUNAS_MONETARIAS:
            valor_total = formatar_moeda(
                tabela_df[coluna].sum()
            )
            estilo_total = estilo_total_numero

        else:
            valor_total = ""
            estilo_total = estilo_total_texto

        linha_total.append(
            criar_paragrafo(
                valor_total,
                estilo_total,
            )
        )

    dados_tabela.append(
        linha_total
    )

    largura_colunas = [
        1.75 * cm,  # Data
        2.15 * cm,  # Número
        3.30 * cm,  # Paciente
        2.25 * cm,  # Convênio
        2.70 * cm,  # Médico
        2.80 * cm,  # Exame
        3.70 * cm,  # Procedimentos
        2.05 * cm,  # Valor exame
        2.05 * cm,  # Taxa
    ]

    tabela_pdf = Table(
        dados_tabela,
        colWidths=largura_colunas,
        repeatRows=1,
        hAlign="LEFT",
    )

    tabela_pdf.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#404040"),
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.25,
                    colors.HexColor("#C8C8C8"),
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    3,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    3,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    3,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    3,
                ),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -2),
                    [
                        colors.white,
                        colors.HexColor("#F7F7F7"),
                    ],
                ),
                (
                    "BACKGROUND",
                    (0, -1),
                    (-1, -1),
                    colors.HexColor("#E0E0E0"),
                ),
                (
                    "LINEABOVE",
                    (0, -1),
                    (-1, -1),
                    0.75,
                    colors.HexColor("#404040"),
                ),
            ]
        )
    )

    elementos.append(
        tabela_pdf
    )

    elementos.append(
        Spacer(
            1,
            0.25 * cm,
        )
    )

    elementos.append(
        Paragraph(
            f"Total de linhas: {len(tabela_df)}",
            estilo_subtitulo,
        )
    )

    documento.build(
        elementos
    )

    pdf_bytes = buffer.getvalue()

    buffer.close()

    return pdf_bytes


# ============================================================
# Mensagem após salvar
# ============================================================

mensagem_base_dados_salva = st.session_state.pop(
    "mensagem_base_dados_salva",
    None,
)


if mensagem_base_dados_salva:
    st.success(
        mensagem_base_dados_salva
    )


# ============================================================
# Cabeçalho da página
# ============================================================

with st.container(border=True):
    coluna_icone, coluna_titulo = st.columns(
        [1, 8],
        vertical_alignment="center",
    )

    with coluna_icone:
        st.markdown("# 📄")

    with coluna_titulo:
        st.title(
            "Download da planilha"
        )

        st.caption(
            "Gere um PDF com os atendimentos do período selecionado."
        )


# ============================================================
# Carregamento da base
# ============================================================

try:
    with st.spinner(
        "Carregando base de atendimentos..."
    ):
        base_dados_df = get_sheet_data(
            NOME_ABA_BASE_DADOS
        ).copy()

except Exception as error:
    st.error(
        "Não foi possível carregar a base de atendimentos."
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
        COLUNAS_ORIGINAIS,
    )

except ValueError as error:
    st.error(
        str(error)
    )

    st.stop()


# ============================================================
# Tratamento da base
# ============================================================

base_dados_df["data_convertida"] = converter_coluna_data(
    base_dados_df["data"]
)


quantidade_datas_invalidas = int(
    base_dados_df["data_convertida"]
    .isna()
    .sum()
)


if quantidade_datas_invalidas:
    st.warning(
        f"{quantidade_datas_invalidas} registro(s) possuem data "
        "inválida e não serão considerados no relatório."
    )


base_dados_df = base_dados_df.loc[
    base_dados_df["data_convertida"].notna()
].copy()


try:
    for coluna in [
        "valor_exame",
        "taxa_aparelho",
        "valor_medico",
    ]:
        base_dados_df[coluna] = converter_coluna_monetaria(
            base_dados_df[coluna],
            coluna,
        )

except ValueError as error:
    st.error(
        str(error)
    )

    st.stop()


# ============================================================
# Período padrão
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
# Filtro de período
# ============================================================

with st.container(border=True):
    st.markdown(
        "### Período do relatório"
    )

    periodo_selecionado = st.date_input(
        "Selecione o período",
        value=(
            primeiro_dia_mes,
            ultimo_dia_mes,
        ),
        format="DD/MM/YYYY",
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


base_filtrada_df = base_dados_df.loc[
    base_dados_df["data_convertida"].between(
        data_inicial_timestamp,
        data_final_timestamp,
        inclusive="both",
    )
].copy()


base_filtrada_df = base_filtrada_df.sort_values(
    [
        "data_convertida",
        "numero_atendimento",
        "nome_paciente",
        "nome_exame",
    ],
    ascending=[
        True,
        True,
        True,
        True,
    ],
)


tabela_relatorio_df = preparar_tabela_relatorio(
    base_filtrada_df
)


# ============================================================
# Exibição da tabela
# ============================================================

st.markdown(
    "### Prévia da planilha"
)

st.caption(
    f"Atendimentos de {data_inicial.strftime('%d/%m/%Y')} "
    f"até {data_final.strftime('%d/%m/%Y')}."
)


if tabela_relatorio_df.empty:
    st.info(
        "Nenhum atendimento foi encontrado no período selecionado."
    )

else:
    st.dataframe(
        tabela_relatorio_df,
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
            "Convênio": st.column_config.TextColumn(
                "Convênio",
                width="medium",
            ),
            "Médico": st.column_config.TextColumn(
                "Médico",
                width="medium",
            ),
            "Exame": st.column_config.TextColumn(
                "Exame",
                width="large",
            ),
            "Procedimentos": st.column_config.TextColumn(
                "Procedimentos",
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
        },
    )


editar_dados_clicado = st.button(
    "✏️ Editar dados",
    type="secondary",
)

if editar_dados_clicado:
    abrir_dialogo_editar_base_dados()


# ============================================================
# Download do PDF
# ============================================================

st.markdown(
    "### Download"
)


if tabela_relatorio_df.empty:
    st.download_button(
        "⬇️ Baixar PDF",
        data=b"",
        file_name="relatorio_atendimentos.pdf",
        mime="application/pdf",
        disabled=True,
        use_container_width=True,
    )

else:
    pdf_bytes = gerar_pdf_relatorio(
        tabela_df=tabela_relatorio_df,
        data_inicial=data_inicial,
        data_final=data_final,
    )

    nome_arquivo = (
        "relatorio_atendimentos_"
        f"{data_inicial.strftime('%Y%m%d')}_"
        f"a_{data_final.strftime('%Y%m%d')}.pdf"
    )

    st.download_button(
        "⬇️ Baixar PDF",
        data=pdf_bytes,
        file_name=nome_arquivo,
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )