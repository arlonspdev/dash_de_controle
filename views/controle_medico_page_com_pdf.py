from calendar import monthrange
from datetime import date
from html import escape
from io import BytesIO
import re
import unicodedata
import zipfile

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
    PageBreak,
)

from auxiliar.google_sheets import (
    get_or_create_sheet_data,
    get_sheet_data,
)


NOME_ABA_BASE_DADOS = "base_dados"
NOME_ABA_MEDICOS = "lista_medicos"
NOME_ABA_SOBREAVISO = "base_sobreaviso"
NOME_ABA_MEIO_PERIODO = "base_meio_periodo"
NOME_ABA_ISENCAO_MINIMO = "base_isencao_valor_minimo"

TODOS_OS_MEDICOS = "Todos os médicos"

DADOS_EMPRESA = [
    "Arlonsp Serviços Médicos LTDA",
    "Rua Dr. Costa Júnior, 338 ap 113",
    "CEP 05002000",
    "São Paulo- SP",
    "CNPJ 077100220001-94",
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
    Converte as datas da planilha para datetime.
    """
    texto = (
        serie
        .fillna("")
        .astype(str)
        .str.strip()
    )

    # Formato utilizado pelos formulários.
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


def normalizar_texto(valor: str) -> str:
    """
    Normaliza textos para permitir o cruzamento dos nomes
    dos médicos entre diferentes abas.
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


def limpar_nome_arquivo(texto: str) -> str:
    """
    Remove caracteres problemáticos para nome de arquivo.
    """
    texto = normalizar_texto(texto)
    texto = re.sub(r"[^a-z0-9]+", "_", texto)
    texto = texto.strip("_")

    return texto or "medico"


def criar_paragrafo(
    texto,
    estilo: ParagraphStyle,
) -> Paragraph:
    """
    Cria parágrafo seguro para o ReportLab.
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


def dataframe_para_dados_pdf(
    dataframe: pd.DataFrame,
    colunas_monetarias: list[str] | None = None,
) -> list[list[str]]:
    """
    Converte um DataFrame de exibição em lista de listas para PDF.
    """
    colunas_monetarias = colunas_monetarias or []

    dados = [
        list(dataframe.columns)
    ]

    for _, linha in dataframe.iterrows():
        valores_linha = []

        for coluna in dataframe.columns:
            valor = linha[coluna]

            if coluna in colunas_monetarias:
                valores_linha.append(
                    formatar_moeda(valor)
                )

            elif hasattr(valor, "strftime"):
                valores_linha.append(
                    valor.strftime("%d/%m/%Y")
                )

            elif isinstance(valor, bool):
                valores_linha.append(
                    "Sim" if valor else "Não"
                )

            elif pd.isna(valor):
                valores_linha.append("")

            else:
                valores_linha.append(
                    str(valor)
                )

        dados.append(
            valores_linha
        )

    return dados


def criar_tabela_pdf(
    dados: list[list],
    largura_colunas: list[float],
    estilo_texto: ParagraphStyle,
    estilo_numero: ParagraphStyle,
    estilo_cabecalho: ParagraphStyle,
    colunas_numericas: list[int] | None = None,
) -> Table:
    """
    Cria tabela estilizada para o PDF.
    """
    colunas_numericas = colunas_numericas or []

    dados_formatados = []

    for indice_linha, linha in enumerate(dados):
        linha_formatada = []

        for indice_coluna, valor in enumerate(linha):
            if indice_linha == 0:
                estilo = estilo_cabecalho

            elif indice_coluna in colunas_numericas:
                estilo = estilo_numero

            else:
                estilo = estilo_texto

            linha_formatada.append(
                criar_paragrafo(
                    valor,
                    estilo,
                )
            )

        dados_formatados.append(
            linha_formatada
        )

    tabela = Table(
        dados_formatados,
        colWidths=largura_colunas,
        repeatRows=1,
        hAlign="LEFT",
    )

    tabela.setStyle(
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
                    (-1, -1),
                    [
                        colors.white,
                        colors.HexColor("#F7F7F7"),
                    ],
                ),
            ]
        )
    )

    return tabela


def montar_tabela_atendimentos(
    base_filtrada_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Monta a tabela de atendimentos para tela e PDF.
    """
    if base_filtrada_df.empty:
        return pd.DataFrame(
            columns=[
                "Data",
                "Número do atendimento",
                "Paciente",
                "Exame",
                "Valor do exame",
                "Taxa do aparelho",
                "Valor médico",
            ]
        )

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

    tabela_exibicao_df = (
        tabela_exibicao_df.sort_values(
            [
                "data_convertida",
                "numero_atendimento",
            ],
            ascending=[
                True,
                True,
            ],
        )
    )

    tabela_exibicao_df = (
        tabela_exibicao_df.rename(
            columns={
                "data_convertida": "Data",
                "numero_atendimento": (
                    "Número do atendimento"
                ),
                "nome_paciente": "Paciente",
                "nome_exame": "Exame",
                "valor_exame": "Valor do exame",
                "taxa_aparelho": (
                    "Taxa do aparelho"
                ),
                "valor_medico": "Valor médico",
            }
        )
    )

    tabela_exibicao_df["Data"] = (
        tabela_exibicao_df["Data"]
        .dt.date
    )

    return tabela_exibicao_df


def montar_tabela_auxilios(
    auxilios_filtrados_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Monta a tabela de auxílios para tela e PDF.
    """
    if auxilios_filtrados_df.empty:
        return pd.DataFrame(
            columns=[
                "Data",
                "Número do atendimento",
                "Paciente",
                "Médico responsável",
                "Exame",
                "Valor auxílio",
            ]
        )

    tabela_auxilios_df = auxilios_filtrados_df[
        [
            "data_convertida",
            "numero_atendimento",
            "nome_paciente",
            "nome_medico",
            "nome_exame",
            "valor_auxilio",
        ]
    ].copy()

    tabela_auxilios_df = (
        tabela_auxilios_df.sort_values(
            [
                "data_convertida",
                "numero_atendimento",
            ],
            ascending=[
                True,
                True,
            ],
        )
    )

    tabela_auxilios_df = (
        tabela_auxilios_df.rename(
            columns={
                "data_convertida": "Data",
                "numero_atendimento": (
                    "Número do atendimento"
                ),
                "nome_paciente": "Paciente",
                "nome_medico": "Médico responsável",
                "nome_exame": "Exame",
                "valor_auxilio": "Valor auxílio",
            }
        )
    )

    tabela_auxilios_df["Data"] = (
        tabela_auxilios_df["Data"]
        .dt.date
    )

    return tabela_auxilios_df


def montar_tabela_sobreavisos(
    sobreaviso_filtrado_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Monta a tabela de sobreavisos para tela e PDF.
    """
    if sobreaviso_filtrado_df.empty:
        return pd.DataFrame(
            columns=[
                "Data",
                "Valor sobreaviso",
            ]
        )

    tabela_sobreaviso_df = (
        sobreaviso_filtrado_df
        .groupby(
            "data_convertida",
            as_index=False,
        )
        .agg(
            valor=(
                "valor",
                "sum",
            )
        )
        .sort_values(
            "data_convertida"
        )
    )

    tabela_sobreaviso_df = (
        tabela_sobreaviso_df.rename(
            columns={
                "data_convertida": "Data",
                "valor": "Valor sobreaviso",
            }
        )
    )

    tabela_sobreaviso_df["Data"] = (
        tabela_sobreaviso_df["Data"]
        .dt.date
    )

    return tabela_sobreaviso_df


def montar_tabela_pagamentos_minimos(
    resumo_diario_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Monta a tabela de pagamentos pelo mínimo.
    """
    if (
        resumo_diario_df.empty
        or not resumo_diario_df[
            "pagar_valor_minimo"
        ].any()
    ):
        return pd.DataFrame(
            columns=[
                "Data",
                "Meio período",
                "Valor médico calculado",
                "Valor mínimo utilizado",
                "Complemento do mínimo",
                "Valor pago no dia",
            ]
        )

    tabela_pagamentos_minimos_df = (
        resumo_diario_df.loc[
            resumo_diario_df[
                "pagar_valor_minimo"
            ],
            [
                "data_convertida",
                "meio_periodo",
                "valor_medico",
                "valor_minimo_utilizado",
                "complemento_minimo",
                "valor_apos_minimo",
            ],
        ]
        .copy()
        .sort_values(
            "data_convertida"
        )
    )

    tabela_pagamentos_minimos_df = (
        tabela_pagamentos_minimos_df.rename(
            columns={
                "data_convertida": "Data",
                "meio_periodo": "Meio período",
                "valor_medico": (
                    "Valor médico calculado"
                ),
                "valor_minimo_utilizado": (
                    "Valor mínimo utilizado"
                ),
                "complemento_minimo": (
                    "Complemento do mínimo"
                ),
                "valor_apos_minimo": (
                    "Valor pago no dia"
                ),
            }
        )
    )

    tabela_pagamentos_minimos_df["Data"] = (
        tabela_pagamentos_minimos_df[
            "Data"
        ].dt.date
    )

    return tabela_pagamentos_minimos_df


def calcular_dados_medico(
    medico_selecionado: str,
    data_inicial_timestamp: pd.Timestamp,
    data_final_timestamp: pd.Timestamp,
    base_dados_df: pd.DataFrame,
    lista_medicos_df: pd.DataFrame,
    base_sobreaviso_df: pd.DataFrame,
    base_meio_periodo_df: pd.DataFrame,
    base_isencao_minimo_df: pd.DataFrame,
) -> dict:
    """
    Calcula todos os dados de um médico no período.
    """
    medico_selecionado_normalizado = normalizar_texto(
        medico_selecionado
    )

    registro_medico = lista_medicos_df.loc[
        lista_medicos_df[
            "medico_normalizado"
        ].eq(
            medico_selecionado_normalizado
        )
    ]

    if registro_medico.empty:
        valor_minimo_medico = 0.0
        pix_medico = ""

    else:
        valor_minimo_medico = float(
            registro_medico.iloc[0][
                "valor_minimo"
            ]
        )

        pix_medico = str(
            registro_medico.iloc[0].get(
                "pix",
                "",
            )
            or ""
        ).strip()

    base_filtrada_df = base_dados_df.loc[
        base_dados_df["data_convertida"].between(
            data_inicial_timestamp,
            data_final_timestamp,
            inclusive="both",
        )
        & base_dados_df["medico_normalizado"].eq(
            medico_selecionado_normalizado
        )
    ].copy()

    auxilios_filtrados_df = base_dados_df.loc[
        base_dados_df["data_convertida"].between(
            data_inicial_timestamp,
            data_final_timestamp,
            inclusive="both",
        )
        & base_dados_df[
            "medico_auxiliar_normalizado"
        ].eq(
            medico_selecionado_normalizado
        )
        & (
            base_dados_df["valor_auxilio"] > 0
        )
    ].copy()

    sobreaviso_filtrado_df = base_sobreaviso_df.loc[
        base_sobreaviso_df["data_convertida"].between(
            data_inicial_timestamp,
            data_final_timestamp,
            inclusive="both",
        )
        & base_sobreaviso_df[
            "medico_normalizado"
        ].eq(
            medico_selecionado_normalizado
        )
    ].copy()

    meio_periodo_filtrado_df = base_meio_periodo_df.loc[
        base_meio_periodo_df["data_convertida"].between(
            data_inicial_timestamp,
            data_final_timestamp,
            inclusive="both",
        )
        & base_meio_periodo_df[
            "medico_normalizado"
        ].eq(
            medico_selecionado_normalizado
        )
    ].copy()

    datas_meio_periodo = set(
        meio_periodo_filtrado_df[
            "data_convertida"
        ].tolist()
    )

    isencao_minimo_filtrado_df = base_isencao_minimo_df.loc[
        base_isencao_minimo_df["data_convertida"].between(
            data_inicial_timestamp,
            data_final_timestamp,
            inclusive="both",
        )
        & base_isencao_minimo_df[
            "medico_normalizado"
        ].eq(
            medico_selecionado_normalizado
        )
    ].copy()

    datas_isentas_valor_minimo = set(
        isencao_minimo_filtrado_df[
            "data_convertida"
        ].tolist()
    )

    # Um atendimento pode ocupar várias linhas por causa dos
    # exames e procedimentos. Por isso, a contagem utiliza
    # chave_atendimento, sem duplicidades.
    total_atendimentos = len(
        base_filtrada_df[
            [
                "data_convertida",
                "chave_atendimento",
            ]
        ]
        .drop_duplicates()
    )

    total_valor_exame = base_filtrada_df[
        "valor_exame"
    ].sum()

    total_taxa_aparelho = base_filtrada_df[
        "taxa_aparelho"
    ].sum()

    total_valor_medico = base_filtrada_df[
        "valor_medico"
    ].sum()

    total_auxilio = auxilios_filtrados_df[
        "valor_auxilio"
    ].sum()

    quantidade_auxilios = len(
        auxilios_filtrados_df[
            [
                "data_convertida",
                "chave_atendimento",
            ]
        ]
        .drop_duplicates()
    )

    if base_filtrada_df.empty:
        resumo_diario_df = pd.DataFrame(
            columns=[
                "data_convertida",
                "valor_medico",
                "meio_periodo",
                "valor_minimo_utilizado",
                "pagar_valor_minimo",
                "complemento_minimo",
                "valor_apos_minimo",
            ]
        )

        total_apos_minimo = 0.0
        quantidade_dias_valor_minimo = 0

    else:
        resumo_diario_df = (
            base_filtrada_df
            .groupby(
                "data_convertida",
                as_index=False,
            )
            .agg(
                valor_medico=(
                    "valor_medico",
                    "sum",
                )
            )
        )

        resumo_diario_df["meio_periodo"] = (
            resumo_diario_df[
                "data_convertida"
            ].isin(
                datas_meio_periodo
            )
        )

        # O valor cadastrado em lista_medicos representa
        # o mínimo para dois períodos.
        resumo_diario_df[
            "valor_minimo_utilizado"
        ] = valor_minimo_medico

        resumo_diario_df.loc[
            resumo_diario_df["meio_periodo"],
            "valor_minimo_utilizado",
        ] = (
            valor_minimo_medico / 2
        )

        resumo_diario_df[
            "pagar_valor_minimo"
        ] = (
            resumo_diario_df[
                "valor_medico"
            ]
            < resumo_diario_df[
                "valor_minimo_utilizado"
            ]
        )

        resumo_diario_df[
            "valor_apos_minimo"
        ] = resumo_diario_df[
            [
                "valor_medico",
                "valor_minimo_utilizado",
            ]
        ].max(axis=1)

        resumo_diario_df[
            "complemento_minimo"
        ] = (
            resumo_diario_df[
                "valor_apos_minimo"
            ]
            - resumo_diario_df[
                "valor_medico"
            ]
        ).clip(
            lower=0
        )

        # Isenção manual: dias marcados na página de controle
        # financeiro em que o valor mínimo não deve ser
        # calculado, mesmo que o valor do médico fique abaixo
        # do mínimo.
        resumo_diario_df["isento_valor_minimo"] = (
            resumo_diario_df["data_convertida"].isin(
                datas_isentas_valor_minimo
            )
        )

        resumo_diario_df.loc[
            resumo_diario_df["isento_valor_minimo"],
            "pagar_valor_minimo",
        ] = False

        resumo_diario_df.loc[
            resumo_diario_df["isento_valor_minimo"],
            "valor_apos_minimo",
        ] = (
            resumo_diario_df.loc[
                resumo_diario_df["isento_valor_minimo"],
                "valor_medico",
            ]
        )

        resumo_diario_df[
            "complemento_minimo"
        ] = (
            resumo_diario_df[
                "valor_apos_minimo"
            ]
            - resumo_diario_df[
                "valor_medico"
            ]
        ).clip(
            lower=0
        )

        total_apos_minimo = resumo_diario_df[
            "valor_apos_minimo"
        ].sum()

        quantidade_dias_valor_minimo = int(
            resumo_diario_df[
                "pagar_valor_minimo"
            ].sum()
        )

    total_sobreaviso = sobreaviso_filtrado_df[
        "valor"
    ].sum()

    # O valor final considera:
    # 1. valor dos atendimentos após o mínimo diário;
    # 2. sobreaviso;
    # 3. auxílio.
    # O auxílio não entra no cálculo do valor mínimo.
    total_final_medico = (
        total_apos_minimo
        + total_sobreaviso
        + total_auxilio
    )

    tabela_atendimentos_df = montar_tabela_atendimentos(
        base_filtrada_df
    )

    tabela_auxilios_df = montar_tabela_auxilios(
        auxilios_filtrados_df
    )

    tabela_sobreaviso_df = montar_tabela_sobreavisos(
        sobreaviso_filtrado_df
    )

    tabela_pagamentos_minimos_df = montar_tabela_pagamentos_minimos(
        resumo_diario_df
    )

    return {
        "medico": medico_selecionado,
        "pix": pix_medico,
        "valor_minimo_medico": valor_minimo_medico,
        "base_filtrada_df": base_filtrada_df,
        "auxilios_filtrados_df": auxilios_filtrados_df,
        "sobreaviso_filtrado_df": sobreaviso_filtrado_df,
        "resumo_diario_df": resumo_diario_df,
        "tabela_atendimentos_df": tabela_atendimentos_df,
        "tabela_auxilios_df": tabela_auxilios_df,
        "tabela_sobreaviso_df": tabela_sobreaviso_df,
        "tabela_pagamentos_minimos_df": tabela_pagamentos_minimos_df,
        "total_atendimentos": total_atendimentos,
        "total_valor_exame": total_valor_exame,
        "total_taxa_aparelho": total_taxa_aparelho,
        "total_valor_medico": total_valor_medico,
        "total_auxilio": total_auxilio,
        "quantidade_auxilios": quantidade_auxilios,
        "total_sobreaviso": total_sobreaviso,
        "total_apos_minimo": total_apos_minimo,
        "total_final_medico": total_final_medico,
        "quantidade_dias_valor_minimo": quantidade_dias_valor_minimo,
    }


def medico_tem_movimento(
    dados_medico: dict,
) -> bool:
    """
    Verifica se o médico possui algum valor ou registro no período.
    """
    return any(
        [
            dados_medico["total_atendimentos"] > 0,
            dados_medico["quantidade_auxilios"] > 0,
            dados_medico["total_sobreaviso"] > 0,
        ]
    )


def gerar_pdf_medico(
    dados_medico: dict,
    data_inicial: date,
    data_final: date,
) -> bytes:
    """
    Gera o PDF de produção de um médico.
    """
    buffer = BytesIO()

    documento = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=0.7 * cm,
        leftMargin=0.7 * cm,
        topMargin=0.7 * cm,
        bottomMargin=0.7 * cm,
        title="Resumo de produção médica",
    )

    estilo_titulo = ParagraphStyle(
        "Titulo",
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        alignment=TA_CENTER,
        spaceAfter=6,
    )

    estilo_subtitulo = ParagraphStyle(
        "Subtitulo",
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        spaceAfter=8,
    )

    estilo_secao = ParagraphStyle(
        "Secao",
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        alignment=TA_LEFT,
        spaceBefore=8,
        spaceAfter=5,
    )

    estilo_texto = ParagraphStyle(
        "Texto",
        fontName="Helvetica",
        fontSize=7,
        leading=8.5,
        alignment=TA_LEFT,
    )

    estilo_numero = ParagraphStyle(
        "Numero",
        fontName="Helvetica",
        fontSize=7,
        leading=8.5,
        alignment=TA_RIGHT,
    )

    estilo_cabecalho = ParagraphStyle(
        "CabecalhoTabela",
        fontName="Helvetica-Bold",
        fontSize=6.7,
        leading=8,
        alignment=TA_CENTER,
        textColor=colors.white,
    )

    estilo_tabela = ParagraphStyle(
        "Tabela",
        fontName="Helvetica",
        fontSize=6.5,
        leading=7.8,
        alignment=TA_LEFT,
    )

    estilo_tabela_numero = ParagraphStyle(
        "TabelaNumero",
        fontName="Helvetica",
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
            "Resumo de produção médica",
            estilo_titulo,
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
            0.15 * cm,
        )
    )

    dados_empresa_pix = [
        [
            criar_paragrafo("Dados da empresa", estilo_cabecalho),
            criar_paragrafo("Dados do médico", estilo_cabecalho),
        ],
        [
            criar_paragrafo("\n".join(DADOS_EMPRESA), estilo_texto),
            criar_paragrafo(
                "\n".join(
                    [
                        f"Médico: {dados_medico['medico']}",
                        f"PIX: {dados_medico['pix'] or 'Não informado'}",
                    ]
                ),
                estilo_texto,
            ),
        ],
    ]

    tabela_empresa_pix = Table(
        dados_empresa_pix,
        colWidths=[
            13.7 * cm,
            13.7 * cm,
        ],
        hAlign="LEFT",
    )

    tabela_empresa_pix.setStyle(
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
                    5,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
            ]
        )
    )

    elementos.append(
        tabela_empresa_pix
    )

    elementos.append(
        Paragraph(
            "Resumo financeiro",
            estilo_secao,
        )
    )

    resumo_financeiro = pd.DataFrame(
        [
            {
                "Indicador": "Total de atendimentos",
                "Valor": dados_medico["total_atendimentos"],
            },
            {
                "Indicador": "Valor dos exames",
                "Valor": formatar_moeda(
                    dados_medico["total_valor_exame"]
                ),
            },
            {
                "Indicador": "Taxa do aparelho",
                "Valor": formatar_moeda(
                    dados_medico["total_taxa_aparelho"]
                ),
            },
            {
                "Indicador": "Valor médico antes do mínimo",
                "Valor": formatar_moeda(
                    dados_medico["total_valor_medico"]
                ),
            },
            {
                "Indicador": "Valor após mínimo",
                "Valor": formatar_moeda(
                    dados_medico["total_apos_minimo"]
                ),
            },
            {
                "Indicador": "Valor auxílio",
                "Valor": formatar_moeda(
                    dados_medico["total_auxilio"]
                ),
            },
            {
                "Indicador": "Valor sobreaviso",
                "Valor": formatar_moeda(
                    dados_medico["total_sobreaviso"]
                ),
            },
            {
                "Indicador": "Valor final médico",
                "Valor": formatar_moeda(
                    dados_medico["total_final_medico"]
                ),
            },
            {
                "Indicador": "Valor mínimo dois períodos",
                "Valor": formatar_moeda(
                    dados_medico["valor_minimo_medico"]
                ),
            },
            {
                "Indicador": "Valor mínimo meio período",
                "Valor": formatar_moeda(
                    dados_medico["valor_minimo_medico"] / 2
                ),
            },
            {
                "Indicador": "Dias com pagamento mínimo",
                "Valor": dados_medico[
                    "quantidade_dias_valor_minimo"
                ],
            },
        ]
    )

    elementos.append(
        criar_tabela_pdf(
            dados=dataframe_para_dados_pdf(
                resumo_financeiro
            ),
            largura_colunas=[
                8.0 * cm,
                5.0 * cm,
            ],
            estilo_texto=estilo_texto,
            estilo_numero=estilo_numero,
            estilo_cabecalho=estilo_cabecalho,
            colunas_numericas=[],
        )
    )

    elementos.append(
        Paragraph(
            "Atendimentos",
            estilo_secao,
        )
    )

    tabela_atendimentos_df = dados_medico[
        "tabela_atendimentos_df"
    ]

    if tabela_atendimentos_df.empty:
        elementos.append(
            Paragraph(
                "Nenhum atendimento encontrado no período.",
                estilo_texto,
            )
        )

    else:
        elementos.append(
            criar_tabela_pdf(
                dados=dataframe_para_dados_pdf(
                    tabela_atendimentos_df,
                    colunas_monetarias=[
                        "Valor do exame",
                        "Taxa do aparelho",
                        "Valor médico",
                    ],
                ),
                largura_colunas=[
                    1.7 * cm,
                    2.4 * cm,
                    4.2 * cm,
                    4.4 * cm,
                    2.4 * cm,
                    2.4 * cm,
                    2.4 * cm,
                ],
                estilo_texto=estilo_tabela,
                estilo_numero=estilo_tabela_numero,
                estilo_cabecalho=estilo_cabecalho,
                colunas_numericas=[
                    4,
                    5,
                    6,
                ],
            )
        )

    elementos.append(
        Paragraph(
            "Auxílios",
            estilo_secao,
        )
    )

    tabela_auxilios_df = dados_medico[
        "tabela_auxilios_df"
    ]

    if tabela_auxilios_df.empty:
        elementos.append(
            Paragraph(
                "Nenhum auxílio encontrado no período.",
                estilo_texto,
            )
        )

    else:
        elementos.append(
            criar_tabela_pdf(
                dados=dataframe_para_dados_pdf(
                    tabela_auxilios_df,
                    colunas_monetarias=[
                        "Valor auxílio",
                    ],
                ),
                largura_colunas=[
                    1.7 * cm,
                    2.4 * cm,
                    4.1 * cm,
                    4.1 * cm,
                    4.1 * cm,
                    2.4 * cm,
                ],
                estilo_texto=estilo_tabela,
                estilo_numero=estilo_tabela_numero,
                estilo_cabecalho=estilo_cabecalho,
                colunas_numericas=[
                    5,
                ],
            )
        )

    elementos.append(
        Paragraph(
            "Sobreavisos",
            estilo_secao,
        )
    )

    tabela_sobreaviso_df = dados_medico[
        "tabela_sobreaviso_df"
    ]

    if tabela_sobreaviso_df.empty:
        elementos.append(
            Paragraph(
                "Nenhum sobreaviso encontrado no período.",
                estilo_texto,
            )
        )

    else:
        elementos.append(
            criar_tabela_pdf(
                dados=dataframe_para_dados_pdf(
                    tabela_sobreaviso_df,
                    colunas_monetarias=[
                        "Valor sobreaviso",
                    ],
                ),
                largura_colunas=[
                    2.5 * cm,
                    4.0 * cm,
                ],
                estilo_texto=estilo_tabela,
                estilo_numero=estilo_tabela_numero,
                estilo_cabecalho=estilo_cabecalho,
                colunas_numericas=[
                    1,
                ],
            )
        )

    elementos.append(
        Paragraph(
            "Pagamentos pelo valor mínimo",
            estilo_secao,
        )
    )

    tabela_pagamentos_minimos_df = dados_medico[
        "tabela_pagamentos_minimos_df"
    ]

    if tabela_pagamentos_minimos_df.empty:
        elementos.append(
            Paragraph(
                "Nenhum pagamento pelo valor mínimo foi necessário no período.",
                estilo_texto,
            )
        )

    else:
        elementos.append(
            criar_tabela_pdf(
                dados=dataframe_para_dados_pdf(
                    tabela_pagamentos_minimos_df,
                    colunas_monetarias=[
                        "Valor médico calculado",
                        "Valor mínimo utilizado",
                        "Complemento do mínimo",
                        "Valor pago no dia",
                    ],
                ),
                largura_colunas=[
                    1.8 * cm,
                    2.2 * cm,
                    3.2 * cm,
                    3.2 * cm,
                    3.2 * cm,
                    3.2 * cm,
                ],
                estilo_texto=estilo_tabela,
                estilo_numero=estilo_tabela_numero,
                estilo_cabecalho=estilo_cabecalho,
                colunas_numericas=[
                    2,
                    3,
                    4,
                    5,
                ],
            )
        )

    documento.build(
        elementos
    )

    pdf_bytes = buffer.getvalue()

    buffer.close()

    return pdf_bytes


def gerar_zip_pdfs(
    lista_dados_medicos: list[dict],
    data_inicial: date,
    data_final: date,
) -> bytes:
    """
    Gera um ZIP com um PDF por médico.
    """
    buffer_zip = BytesIO()

    with zipfile.ZipFile(
        buffer_zip,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as arquivo_zip:
        for dados_medico in lista_dados_medicos:
            pdf_bytes = gerar_pdf_medico(
                dados_medico=dados_medico,
                data_inicial=data_inicial,
                data_final=data_final,
            )

            nome_arquivo = (
                "resumo_producao_"
                f"{limpar_nome_arquivo(dados_medico['medico'])}_"
                f"{data_inicial.strftime('%Y%m%d')}_"
                f"a_{data_final.strftime('%Y%m%d')}.pdf"
            )

            arquivo_zip.writestr(
                nome_arquivo,
                pdf_bytes,
            )

    zip_bytes = buffer_zip.getvalue()

    buffer_zip.close()

    return zip_bytes


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
        st.title(
            "Controle financeiro por médico"
        )

        st.caption(
            "ARLONSP - SERVIÇOS MÉDICOS | "
            "Consulta individual dos atendimentos"
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

        base_isencao_minimo_df = get_or_create_sheet_data(
            NOME_ABA_ISENCAO_MINIMO,
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


# Caso a aba esteja completamente vazia.
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


if (
    base_isencao_minimo_df.empty
    and len(base_isencao_minimo_df.columns) == 0
):
    base_isencao_minimo_df = pd.DataFrame(
        columns=[
            "data",
            "medico",
        ]
    )


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

base_isencao_minimo_df.columns = (
    base_isencao_minimo_df.columns
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
            "numero_atendimento",
            "nome_paciente",
            "nome_medico",
            "nome_exame",
            "valor_exame",
            "taxa_aparelho",
            "valor_medico",
            "medico_auxiliar",
            "valor_auxilio",
        ],
    )

    validar_colunas(
        lista_medicos_df,
        NOME_ABA_MEDICOS,
        [
            "nome_medico",
            "valor_minimo",
            "pix",
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

    validar_colunas(
        base_isencao_minimo_df,
        NOME_ABA_ISENCAO_MINIMO,
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
# Tratamento da lista de médicos
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

lista_medicos_df["pix"] = (
    lista_medicos_df["pix"]
    .fillna("")
    .astype(str)
    .str.strip()
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
        "Será utilizado o último valor mínimo e PIX cadastrado para: "
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
    .reset_index(drop=True)
)


nomes_medicos = sorted(
    lista_medicos_df[
        "nome_medico"
    ]
    .dropna()
    .astype(str)
    .str.strip()
    .tolist(),
    key=normalizar_texto,
)


if not nomes_medicos:
    st.warning(
        "Nenhum médico foi encontrado na aba "
        "`lista_medicos`."
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

base_dados_df["medico_normalizado"] = (
    base_dados_df["nome_medico"]
    .apply(normalizar_texto)
)

base_dados_df["medico_auxiliar"] = (
    base_dados_df["medico_auxiliar"]
    .fillna("")
    .astype(str)
    .str.strip()
)

base_dados_df["medico_auxiliar_normalizado"] = (
    base_dados_df["medico_auxiliar"]
    .apply(normalizar_texto)
)

base_dados_df["numero_atendimento"] = (
    base_dados_df["numero_atendimento"]
    .fillna("")
    .astype(str)
    .str.strip()
)

base_dados_df["nome_paciente"] = (
    base_dados_df["nome_paciente"]
    .fillna("")
    .astype(str)
    .str.strip()
)

base_dados_df["nome_exame"] = (
    base_dados_df["nome_exame"]
    .fillna("")
    .astype(str)
    .str.strip()
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
        "considerados."
    )


base_dados_df = base_dados_df.loc[
    base_dados_df["data_convertida"].notna()
    & (
        base_dados_df["medico_normalizado"].ne("")
        | base_dados_df[
            "medico_auxiliar_normalizado"
        ].ne("")
    )
].copy()


base_dados_df["chave_atendimento"] = (
    base_dados_df["numero_atendimento"]
)


sem_numero_atendimento = (
    base_dados_df[
        "chave_atendimento"
    ].eq("")
)


base_dados_df.loc[
    sem_numero_atendimento,
    "chave_atendimento",
] = (
    "__linha_"
    + base_dados_df.loc[
        sem_numero_atendimento
    ].index.astype(str)
)


try:
    for coluna_monetaria in [
        "valor_exame",
        "taxa_aparelho",
        "valor_medico",
        "valor_auxilio",
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
        "serão considerados."
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
        "não serão considerados."
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
    .drop_duplicates(
        subset=[
            "data_convertida",
            "medico_normalizado",
        ],
        keep="last",
    )
    .copy()
)


# ============================================================
# Tratamento da base de isenção do valor mínimo
# ============================================================

base_isencao_minimo_df["medico"] = (
    base_isencao_minimo_df["medico"]
    .fillna("")
    .astype(str)
    .str.strip()
)

base_isencao_minimo_df["medico_normalizado"] = (
    base_isencao_minimo_df["medico"]
    .apply(normalizar_texto)
)

base_isencao_minimo_df["data_convertida"] = (
    converter_coluna_data(
        base_isencao_minimo_df["data"]
    )
)


base_isencao_minimo_df = (
    base_isencao_minimo_df.loc[
        base_isencao_minimo_df[
            "data_convertida"
        ].notna()
        & base_isencao_minimo_df[
            "medico_normalizado"
        ].ne("")
    ]
    .drop_duplicates(
        subset=[
            "data_convertida",
            "medico_normalizado",
        ],
        keep="last",
    )
    .copy()
)


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
                *nomes_medicos,
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
# Modo todos os médicos
# ============================================================

if medico_selecionado == TODOS_OS_MEDICOS:
    st.markdown(
        "### Download dos PDFs"
    )

    st.caption(
        "Quando a opção Todos os médicos está selecionada, "
        "a página não mostra o resumo na tela. O botão abaixo "
        "gera um arquivo ZIP com um PDF por médico que possui "
        "atendimento, auxílio ou sobreaviso no período."
    )

    dados_medicos_para_zip = []

    for nome_medico in nomes_medicos:
        dados_medico = calcular_dados_medico(
            medico_selecionado=nome_medico,
            data_inicial_timestamp=data_inicial_timestamp,
            data_final_timestamp=data_final_timestamp,
            base_dados_df=base_dados_df,
            lista_medicos_df=lista_medicos_df,
            base_sobreaviso_df=base_sobreaviso_df,
            base_meio_periodo_df=base_meio_periodo_df,
            base_isencao_minimo_df=base_isencao_minimo_df,
        )

        if medico_tem_movimento(
            dados_medico
        ):
            dados_medicos_para_zip.append(
                dados_medico
            )

    if not dados_medicos_para_zip:
        st.info(
            "Nenhum médico possui atendimento, auxílio ou "
            "sobreaviso no período selecionado."
        )

        st.download_button(
            "⬇️ Baixar ZIP com PDFs",
            data=b"",
            file_name="resumos_medicos.zip",
            mime="application/zip",
            disabled=True,
            use_container_width=True,
        )

        st.stop()

    zip_bytes = gerar_zip_pdfs(
        lista_dados_medicos=dados_medicos_para_zip,
        data_inicial=data_inicial,
        data_final=data_final,
    )

    nome_zip = (
        "resumos_medicos_"
        f"{data_inicial.strftime('%Y%m%d')}_"
        f"a_{data_final.strftime('%Y%m%d')}.zip"
    )

    st.download_button(
        "⬇️ Baixar ZIP com PDFs",
        data=zip_bytes,
        file_name=nome_zip,
        mime="application/zip",
        type="primary",
        use_container_width=True,
    )

    st.caption(
        f"O ZIP contém {len(dados_medicos_para_zip)} PDF(s)."
    )

    st.stop()


# ============================================================
# Modo médico individual
# ============================================================

dados_medico = calcular_dados_medico(
    medico_selecionado=medico_selecionado,
    data_inicial_timestamp=data_inicial_timestamp,
    data_final_timestamp=data_final_timestamp,
    base_dados_df=base_dados_df,
    lista_medicos_df=lista_medicos_df,
    base_sobreaviso_df=base_sobreaviso_df,
    base_meio_periodo_df=base_meio_periodo_df,
    base_isencao_minimo_df=base_isencao_minimo_df,
)


if not dados_medico["pix"]:
    st.warning(
        "O médico selecionado não possui PIX cadastrado "
        "na coluna `pix` da aba `lista_medicos`."
    )


# ============================================================
# Botão de download individual
# ============================================================

with st.container(border=True):
    st.markdown(
        "### Download do PDF"
    )

    st.caption(
        "O PDF contém o resumo financeiro do médico, "
        "os dados da empresa e o PIX cadastrado na aba "
        "`lista_medicos`."
    )

    pdf_bytes = gerar_pdf_medico(
        dados_medico=dados_medico,
        data_inicial=data_inicial,
        data_final=data_final,
    )

    nome_pdf = (
        "resumo_producao_"
        f"{limpar_nome_arquivo(medico_selecionado)}_"
        f"{data_inicial.strftime('%Y%m%d')}_"
        f"a_{data_final.strftime('%Y%m%d')}.pdf"
    )

    st.download_button(
        "⬇️ Baixar PDF do médico",
        data=pdf_bytes,
        file_name=nome_pdf,
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )


# ============================================================
# Cards
# ============================================================

st.markdown(
    "### Totais do período"
)


coluna_1, coluna_2, coluna_3 = st.columns(3)

with coluna_1:
    st.metric(
        "Total de atendimentos",
        dados_medico["total_atendimentos"],
        help=(
            "Conta os atendimentos em que o médico foi "
            "registrado como médico responsável."
        ),
    )

with coluna_2:
    st.metric(
        "Valor dos exames",
        formatar_moeda(
            dados_medico["total_valor_exame"]
        ),
    )

with coluna_3:
    st.metric(
        "Taxa do aparelho",
        formatar_moeda(
            dados_medico["total_taxa_aparelho"]
        ),
    )


coluna_4, coluna_5, coluna_6, coluna_7 = st.columns(4)

with coluna_4:
    st.metric(
        "Valor médico",
        formatar_moeda(
            dados_medico["total_valor_medico"]
        ),
        help=(
            "Soma dos valores dos atendimentos antes da "
            "aplicação do valor mínimo diário. "
            "Não inclui auxílio."
        ),
    )

with coluna_5:
    st.metric(
        "Valor auxílio",
        formatar_moeda(
            dados_medico["total_auxilio"]
        ),
        help=(
            "Soma dos valores em que o médico aparece como "
            "médico auxiliar. Esse valor não é usado no "
            "cálculo do mínimo."
        ),
    )

with coluna_6:
    st.metric(
        "Valor sobreaviso",
        formatar_moeda(
            dados_medico["total_sobreaviso"]
        ),
        help=(
            "Soma dos sobreavisos registrados para o médico "
            "no período selecionado."
        ),
    )

with coluna_7:
    st.metric(
        "Valor final médico",
        formatar_moeda(
            dados_medico["total_final_medico"]
        ),
        delta=(
            formatar_moeda(
                dados_medico["total_final_medico"]
                - dados_medico["total_valor_medico"]
            )
            if dados_medico["total_final_medico"]
            > dados_medico["total_valor_medico"]
            else None
        ),
        help=(
            "Total após aplicar o valor mínimo em cada dia "
            "e acrescentar os valores de sobreaviso e auxílio."
        ),
    )


if dados_medico["quantidade_dias_valor_minimo"]:
    resumo_diario_df = dados_medico[
        "resumo_diario_df"
    ]

    quantidade_minimo_meio_periodo = int(
        resumo_diario_df.loc[
            resumo_diario_df[
                "pagar_valor_minimo"
            ],
            "meio_periodo",
        ].sum()
    )

    quantidade_minimo_periodo_completo = (
        dados_medico["quantidade_dias_valor_minimo"]
        - quantidade_minimo_meio_periodo
    )

    st.info(
        f"O pagamento mínimo foi aplicado em "
        f"{dados_medico['quantidade_dias_valor_minimo']} dia(s): "
        f"{quantidade_minimo_meio_periodo} de meio período "
        f"e {quantidade_minimo_periodo_completo} de período "
        "completo. O valor do auxílio não entra nesse cálculo."
    )

else:
    st.caption(
        f"Valor mínimo cadastrado para dois períodos: "
        f"{formatar_moeda(dados_medico['valor_minimo_medico'])}."
    )


# ============================================================
# Tabela de atendimentos sem agrupamento
# ============================================================

st.markdown(
    "### Atendimentos"
)

st.caption(
    f"Atendimentos de {medico_selecionado} entre "
    f"{data_inicial.strftime('%d/%m/%Y')} e "
    f"{data_final.strftime('%d/%m/%Y')}. "
    "Esta tabela considera os registros em que o médico foi "
    "o responsável pelo atendimento."
)


tabela_atendimentos_df = dados_medico[
    "tabela_atendimentos_df"
]


if tabela_atendimentos_df.empty:
    st.info(
        "Nenhum atendimento foi encontrado para o médico "
        "e período selecionados."
    )

else:
    st.dataframe(
        tabela_atendimentos_df,
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
            "Paciente": (
                st.column_config.TextColumn(
                    "Paciente",
                    width="large",
                )
            ),
            "Exame": (
                st.column_config.TextColumn(
                    "Exame",
                    width="large",
                )
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


# ============================================================
# Tabela de auxílios
# ============================================================

st.markdown(
    "### Auxílios"
)

st.caption(
    f"Auxílios de {medico_selecionado} entre "
    f"{data_inicial.strftime('%d/%m/%Y')} e "
    f"{data_final.strftime('%d/%m/%Y')}. "
    "O valor de auxílio é somado ao total final, mas não entra "
    "no cálculo do valor mínimo."
)


tabela_auxilios_df = dados_medico[
    "tabela_auxilios_df"
]


if tabela_auxilios_df.empty:
    st.info(
        "Nenhum auxílio foi encontrado para o médico "
        "e período selecionados."
    )

else:
    st.dataframe(
        tabela_auxilios_df,
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
            "Paciente": (
                st.column_config.TextColumn(
                    "Paciente",
                    width="large",
                )
            ),
            "Médico responsável": (
                st.column_config.TextColumn(
                    "Médico responsável",
                    width="medium",
                )
            ),
            "Exame": (
                st.column_config.TextColumn(
                    "Exame",
                    width="large",
                )
            ),
            "Valor auxílio": (
                st.column_config.NumberColumn(
                    "Valor auxílio",
                    format="R$ %.2f",
                )
            ),
        },
    )

    st.caption(
        f"Total de auxílios no período: "
        f"{formatar_moeda(dados_medico['total_auxilio'])} "
        f"em {dados_medico['quantidade_auxilios']} registro(s)."
    )


# ============================================================
# Tabela de sobreavisos
# ============================================================

st.markdown(
    "### Sobreavisos"
)

st.caption(
    f"Sobreavisos de {medico_selecionado} entre "
    f"{data_inicial.strftime('%d/%m/%Y')} e "
    f"{data_final.strftime('%d/%m/%Y')}."
)


tabela_sobreaviso_df = dados_medico[
    "tabela_sobreaviso_df"
]


if tabela_sobreaviso_df.empty:
    st.info(
        "Nenhum sobreaviso foi encontrado para o médico "
        "e período selecionados."
    )

else:
    st.dataframe(
        tabela_sobreaviso_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Data": st.column_config.DateColumn(
                "Data",
                format="DD/MM/YYYY",
            ),
            "Valor sobreaviso": (
                st.column_config.NumberColumn(
                    "Valor sobreaviso",
                    format="R$ %.2f",
                )
            ),
        },
    )


# ============================================================
# Tabela de pagamentos pelo valor mínimo
# ============================================================

st.markdown(
    "### Pagamentos pelo valor mínimo"
)

st.caption(
    "São exibidos somente os dias em que o valor calculado "
    "pelos atendimentos ficou abaixo do valor mínimo aplicável. "
    "O sobreaviso e o auxílio não estão incluídos no valor "
    "pago nesta tabela."
)


tabela_pagamentos_minimos_df = dados_medico[
    "tabela_pagamentos_minimos_df"
]


if tabela_pagamentos_minimos_df.empty:
    st.info(
        "Nenhum pagamento pelo valor mínimo foi necessário "
        "para o médico e período selecionados."
    )

else:
    st.dataframe(
        tabela_pagamentos_minimos_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Data": (
                st.column_config.DateColumn(
                    "Data",
                    format="DD/MM/YYYY",
                )
            ),
            "Meio período": (
                st.column_config.CheckboxColumn(
                    "Meio período",
                    help=(
                        "Quando marcado, o valor mínimo "
                        "utilizado é metade do valor "
                        "cadastrado para o médico."
                    ),
                )
            ),
            "Valor médico calculado": (
                st.column_config.NumberColumn(
                    "Valor médico calculado",
                    format="R$ %.2f",
                    help=(
                        "Soma dos valores do médico "
                        "antes da aplicação do mínimo. "
                        "Não inclui auxílio."
                    ),
                )
            ),
            "Valor mínimo utilizado": (
                st.column_config.NumberColumn(
                    "Valor mínimo utilizado",
                    format="R$ %.2f",
                    help=(
                        "Valor mínimo completo ou metade "
                        "do mínimo nos dias de meio período."
                    ),
                )
            ),
            "Complemento do mínimo": (
                st.column_config.NumberColumn(
                    "Complemento do mínimo",
                    format="R$ %.2f",
                    help=(
                        "Diferença acrescentada para atingir "
                        "o valor mínimo do dia."
                    ),
                )
            ),
            "Valor pago no dia": (
                st.column_config.NumberColumn(
                    "Valor pago no dia",
                    format="R$ %.2f",
                    help=(
                        "Valor pago pelos atendimentos depois "
                        "da aplicação do mínimo. Não inclui "
                        "sobreaviso nem auxílio."
                    ),
                )
            ),
        },
    )
