import re
import unicodedata

import pandas as pd
import streamlit as st

from auxiliar.google_sheets import (
    get_sheet_data,
    set_sheet_data,
)


URL_PLANILHA = (
    "https://docs.google.com/spreadsheets/d/"
    "17xaXorvF3eyiPKU-4SkWGL2WW8rBB2cmRTrr_PJdCNk/"
)

EMAIL_EDICAO_PLANILHA = "arlonspdev@gmail.com"


BASES_DISPONIVEIS = {
    "Médicos": {
        "aba": "lista_medicos",
        "descricao": "Cadastro dos médicos e valores mínimos.",
    },
    "Exames": {
        "aba": "lista_exames",
        "descricao": "Cadastro dos exames e respectivos valores.",
    },
    "Procedimentos": {
        "aba": "lista_procedimentos",
        "descricao": "Cadastro dos procedimentos disponíveis.",
    },
    "Convênios": {
        "aba": "lista_convenios",
        "descricao": "Cadastro dos convênios disponíveis.",
    },
    "Base de dados": {
        "aba": "base_dados",
        "descricao": "Registros dos atendimentos realizados.",
    },
    "Sobreavisos": {
        "aba": "base_sobreaviso",
        "descricao": (
            "Registros dos períodos de sobreaviso dos médicos."
        ),
    },
    "Outros valores": {
        "aba": "outros_valores",
        "descricao": (
            "Configuração de taxas e outros valores do sistema."
        ),
    },
}


# ============================================================
# Funções auxiliares
# ============================================================

def limpar_dataframe(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Remove linhas totalmente vazias e substitui valores
    NaN por texto vazio.
    """
    dataframe = dataframe.copy()

    dataframe.columns = [
        str(coluna).strip()
        for coluna in dataframe.columns
    ]

    if dataframe.empty:
        return dataframe.reset_index(drop=True)

    linhas_preenchidas = dataframe.apply(
        lambda linha: any(
            pd.notna(valor)
            and str(valor).strip() != ""
            for valor in linha
        ),
        axis=1,
    )

    dataframe = dataframe.loc[
        linhas_preenchidas
    ].copy()

    dataframe = dataframe.where(
        pd.notna(dataframe),
        "",
    )

    return dataframe.reset_index(drop=True)


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
    Converte valores numéricos e monetários para float.

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


def normalizar_texto(valor: str) -> str:
    """
    Remove acentos e trata underline, hífen e espaços
    como equivalentes.
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


def converter_coluna_data(
    serie: pd.Series,
) -> pd.Series:
    """
    Converte datas nos formatos DD/MM/AAAA e AAAA-MM-DD.
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


def obter_valor_sobreaviso_12h(
    outros_valores_df: pd.DataFrame,
) -> float:
    """
    Busca a descrição valor_sobreaviso na aba outros_valores.
    """
    outros_valores_df = outros_valores_df.copy()

    outros_valores_df.columns = (
        outros_valores_df.columns
        .astype(str)
        .str.strip()
    )

    colunas_obrigatorias = {
        "descricao",
        "valor",
    }

    colunas_ausentes = (
        colunas_obrigatorias
        - set(outros_valores_df.columns)
    )

    if colunas_ausentes:
        raise ValueError(
            "A aba 'outros_valores' não possui as colunas: "
            + ", ".join(sorted(colunas_ausentes))
        )

    outros_valores_df["descricao_normalizada"] = (
        outros_valores_df["descricao"]
        .fillna("")
        .apply(normalizar_texto)
    )

    registro = outros_valores_df.loc[
        outros_valores_df[
            "descricao_normalizada"
        ].eq("valor sobreaviso")
    ]

    if registro.empty:
        raise ValueError(
            "A descrição 'valor_sobreaviso' não foi "
            "encontrada na aba 'outros_valores'."
        )

    valor = registro.iloc[-1]["valor"]

    return converter_para_float(valor)


def analisar_erros_sobreaviso(
    dataframe: pd.DataFrame,
    valor_sobreaviso_12h: float,
) -> pd.DataFrame:
    """
    Agrupa os registros de sobreaviso por data e médico.

    Retorna somente os dias em que o valor total ultrapassa
    o equivalente a 24 horas de sobreaviso.
    """
    colunas_resultado = [
        "Data",
        "Médico",
        "Valor total",
        "Horas estimadas",
        "Limite de 24h",
        "Valor excedente",
    ]

    dataframe_vazio = pd.DataFrame(
        columns=colunas_resultado
    )

    if dataframe.empty:
        return dataframe_vazio

    colunas_obrigatorias = {
        "data",
        "medico",
        "valor",
    }

    colunas_ausentes = (
        colunas_obrigatorias
        - set(dataframe.columns)
    )

    if colunas_ausentes:
        raise ValueError(
            "A aba 'base_sobreaviso' não possui as colunas: "
            + ", ".join(sorted(colunas_ausentes))
        )

    if valor_sobreaviso_12h <= 0:
        raise ValueError(
            "O valor de 12h do sobreaviso precisa ser maior "
            "que zero para realizar a validação."
        )

    base = dataframe.copy()

    base["medico"] = (
        base["medico"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    base["data_convertida"] = converter_coluna_data(
        base["data"]
    )

    valores_convertidos = []
    valores_validos = []

    for valor in base["valor"]:
        try:
            valores_convertidos.append(
                converter_para_float(valor)
            )

            valores_validos.append(True)

        except (TypeError, ValueError):
            valores_convertidos.append(0.0)
            valores_validos.append(False)

    base["valor_convertido"] = valores_convertidos
    base["valor_valido"] = valores_validos

    base = base.loc[
        base["data_convertida"].notna()
        & base["medico"].ne("")
        & base["valor_valido"]
    ].copy()

    if base.empty:
        return dataframe_vazio

    resumo = (
        base
        .groupby(
            [
                "data_convertida",
                "medico",
            ],
            as_index=False,
        )
        .agg(
            valor_total=(
                "valor_convertido",
                "sum",
            ),
        )
    )

    limite_24h = valor_sobreaviso_12h * 2

    resumo["horas_estimadas"] = (
        resumo["valor_total"]
        / valor_sobreaviso_12h
        * 12
    )

    resumo["limite_24h"] = limite_24h

    resumo["valor_excedente"] = (
        resumo["valor_total"]
        - limite_24h
    ).clip(lower=0)

    resumo["possui_erro"] = (
        resumo["valor_total"]
        > limite_24h + 0.01
    )

    erros = resumo.loc[
        resumo["possui_erro"]
    ].copy()

    if erros.empty:
        return dataframe_vazio

    erros = erros.sort_values(
        [
            "data_convertida",
            "medico",
        ]
    ).reset_index(drop=True)

    erros = erros.rename(
        columns={
            "data_convertida": "Data",
            "medico": "Médico",
            "valor_total": "Valor total",
            "horas_estimadas": "Horas estimadas",
            "limite_24h": "Limite de 24h",
            "valor_excedente": "Valor excedente",
        }
    )

    erros["Data"] = erros["Data"].dt.date

    return erros[colunas_resultado]


def exibir_tabela_validacao(
    dataframe: pd.DataFrame,
) -> None:
    """
    Exibe a tabela com os dias de sobreaviso que possuem erro.
    """
    st.dataframe(
        dataframe,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Data": st.column_config.DateColumn(
                "Data",
                format="DD/MM/YYYY",
            ),
            "Médico": st.column_config.TextColumn(
                "Médico",
                width="large",
            ),
            "Valor total": (
                st.column_config.NumberColumn(
                    "Valor total",
                    format="R$ %.2f",
                )
            ),
            "Horas estimadas": (
                st.column_config.NumberColumn(
                    "Horas estimadas",
                    format="%.0f h",
                )
            ),
            "Limite de 24h": (
                st.column_config.NumberColumn(
                    "Limite de 24h",
                    format="R$ %.2f",
                )
            ),
            "Valor excedente": (
                st.column_config.NumberColumn(
                    "Valor excedente",
                    format="R$ %.2f",
                )
            ),
        },
    )


@st.dialog(
    "Editar diretamente na planilha",
    width="large",
)
def exibir_dialogo_planilha() -> None:
    """
    Exibe orientações e o link para edição direta
    no Google Sheets.
    """
    st.markdown(
        "### 📊 Edição pelo Google Sheets"
    )

    st.info(
        "A forma recomendada de editar os dados é pela tabela "
        "disponível nesta página. Utilize a planilha diretamente "
        "apenas quando precisar realizar alterações mais amplas "
        "ou específicas."
    )

    st.markdown(
        "Você também pode acessar e editar os dados diretamente "
        "na planilha do sistema."
    )

    st.warning(
        "⚠️ Antes de abrir a planilha, verifique a conta do "
        "Google que está conectada no navegador."
    )

    with st.container(border=True):
        st.markdown(
            "#### Conta necessária para edição"
        )

        st.markdown(
            f"Você precisa estar conectado com o e-mail "
            f"**{EMAIL_EDICAO_PLANILHA}**."
        )

        st.caption(
            "Caso esteja conectado com outro e-mail, a planilha "
            "pode aparecer somente para visualização ou o acesso "
            "pode ser negado."
        )

    st.error(
        "Tome cuidado ao alterar nomes de abas, títulos de colunas "
        "ou a ordem das colunas. Essas mudanças podem impedir o "
        "funcionamento correto do sistema."
    )

    st.link_button(
        "🔗 Abrir planilha no Google Sheets",
        URL_PLANILHA,
        type="primary",
        use_container_width=True,
    )


# ============================================================
# Mensagem após salvar
# ============================================================

mensagem_sucesso = st.session_state.pop(
    "mensagem_configuracao_salva",
    None,
)

if mensagem_sucesso:
    st.success(mensagem_sucesso)


# ============================================================
# Cabeçalho
# ============================================================

with st.container(border=True):
    coluna_icone, coluna_titulo = st.columns(
        [1, 8],
        vertical_alignment="center",
    )

    with coluna_icone:
        st.markdown("# ⚙️")

    with coluna_titulo:
        st.title("Configurações")

        st.caption(
            "Gerencie os cadastros e dados do sistema "
            "ARLONSP - SERVIÇOS MÉDICOS"
        )


# ============================================================
# Seleção da base
# ============================================================

base_selecionada = st.selectbox(
    "Selecione a base que deseja editar",
    options=list(BASES_DISPONIVEIS.keys()),
)

configuracao_base = BASES_DISPONIVEIS[
    base_selecionada
]

nome_aba = configuracao_base["aba"]
descricao_base = configuracao_base["descricao"]

st.info(descricao_base)


# ============================================================
# Carregamento da planilha
# ============================================================

try:
    with st.spinner(
        "Carregando dados da planilha..."
    ):
        dataframe_original = get_sheet_data(
            nome_aba
        ).copy()

except Exception as error:
    st.error(
        f"Não foi possível carregar a aba `{nome_aba}`."
    )

    st.exception(error)
    st.stop()


dataframe_original.columns = (
    dataframe_original.columns
    .astype(str)
    .str.strip()
)


if dataframe_original.columns.duplicated().any():
    colunas_duplicadas = (
        dataframe_original.columns[
            dataframe_original.columns.duplicated()
        ]
        .unique()
        .tolist()
    )

    st.error(
        "A planilha possui nomes de colunas duplicados: "
        + ", ".join(colunas_duplicadas)
    )

    st.stop()


if dataframe_original.empty:
    st.warning(
        "Esta base não possui registros. Você pode adicionar "
        "novas linhas diretamente na tabela abaixo."
    )


# ============================================================
# Tabela editável
# ============================================================

st.subheader(base_selecionada)

st.caption(
    "Você pode alterar células, adicionar novas linhas ou excluir "
    "linhas. As alterações só serão enviadas à base "
    "quando você clicar em salvar."
)


dataframe_editado = st.data_editor(
    dataframe_original,
    use_container_width=True,
    hide_index=True,
    num_rows="dynamic",
    key=f"editor_configuracao_{nome_aba}",
)


dataframe_editado_limpo = limpar_dataframe(
    dataframe_editado
)


quantidade_original = len(
    dataframe_original
)

quantidade_editada = len(
    dataframe_editado_limpo
)


coluna_registros, coluna_aba = st.columns(2)

with coluna_registros:
    st.metric(
        "Quantidade de registros",
        quantidade_editada,
        delta=(
            quantidade_editada
            - quantidade_original
        ),
    )

with coluna_aba:
    st.metric(
        "Aba selecionada",
        nome_aba,
    )


# ============================================================
# Calcula a validação dos sobreavisos
# ============================================================

valor_sobreaviso_12h = 0.0
erros_sobreaviso_df = pd.DataFrame()
erro_ao_validar_sobreaviso = None


if nome_aba == "base_sobreaviso":
    try:
        outros_valores_df = get_sheet_data(
            "outros_valores"
        ).copy()

        valor_sobreaviso_12h = (
            obter_valor_sobreaviso_12h(
                outros_valores_df
            )
        )

        erros_sobreaviso_df = (
            analisar_erros_sobreaviso(
                dataframe_editado_limpo,
                valor_sobreaviso_12h,
            )
        )

    except Exception as error:
        erro_ao_validar_sobreaviso = error


# ============================================================
# Salvamento
# ============================================================

st.warning(
    f"Ao salvar, todo o conteúdo da aba `{nome_aba}` será "
    "substituído pelos dados exibidos na tabela."
)


salvar_alteracoes = st.button(
    "💾 Salvar alterações",
    type="primary",
    use_container_width=True,
)


if salvar_alteracoes:
    dataframe_para_salvar = (
        dataframe_editado_limpo.copy()
    )

    bloquear_salvamento = False

    if nome_aba == "base_sobreaviso":
        if erro_ao_validar_sobreaviso is not None:
            st.error(
                "Não foi possível validar os registros de "
                "sobreaviso. As alterações não foram salvas."
            )

            st.exception(
                erro_ao_validar_sobreaviso
            )

            bloquear_salvamento = True

        elif not erros_sobreaviso_df.empty:
            st.error(
                "As alterações não foram salvas. Corrija "
                "primeiro os dias com mais de 24 horas de "
                "sobreaviso."
            )

            bloquear_salvamento = True

    if not bloquear_salvamento:
        try:
            with st.spinner(
                "Salvando alterações..."
            ):
                set_sheet_data(
                    nome_aba,
                    dataframe_para_salvar,
                )

            st.session_state[
                "mensagem_configuracao_salva"
            ] = (
                f"As alterações da base "
                f"“{base_selecionada}” foram salvas "
                "com sucesso."
            )

            st.rerun()

        except Exception as error:
            st.error(
                f"Não foi possível salvar as alterações "
                f"na aba `{nome_aba}`."
            )

            st.exception(error)


# ============================================================
# Edição alternativa pelo Google Sheets
# ============================================================

st.caption(
    "Precisa realizar uma alteração mais ampla? "
    "Existe uma opção alternativa de edição."
)

coluna_espaco, coluna_editar_planilha = st.columns(
    [3, 1]
)

with coluna_editar_planilha:
    abrir_planilha = st.button(
        "📊 Editar na planilha",
        type="secondary",
        use_container_width=True,
    )


if abrir_planilha:
    exibir_dialogo_planilha()


# ============================================================
# Validação dos sobreavisos
# ============================================================

if nome_aba == "base_sobreaviso":
    st.divider()

    st.markdown("### Validação dos sobreavisos")

    st.caption(
        "O valor cadastrado representa um período de 12 horas. "
        "Um médico não pode possuir mais de 24 horas de "
        "sobreaviso no mesmo dia."
    )

    if erro_ao_validar_sobreaviso is not None:
        st.error(
            "Não foi possível validar os registros "
            "de sobreaviso."
        )

        st.exception(
            erro_ao_validar_sobreaviso
        )

    else:
        limite_24h = valor_sobreaviso_12h * 2

        quantidade_erros = len(
            erros_sobreaviso_df
        )

        coluna_valor_12h, coluna_limite, coluna_erros = (
            st.columns(3)
        )

        with coluna_valor_12h:
            st.metric(
                "Valor de 12h",
                formatar_moeda(
                    valor_sobreaviso_12h
                ),
            )

        with coluna_limite:
            st.metric(
                "Limite diário de 24h",
                formatar_moeda(
                    limite_24h
                ),
            )

        with coluna_erros:
            st.metric(
                "Dias com erro",
                quantidade_erros,
            )

        if quantidade_erros > 0:
            st.error(
                f"Foram encontrados {quantidade_erros} "
                "dia(s) com mais de 24 horas de sobreaviso "
                "para o mesmo médico."
            )

            st.markdown(
                "#### Dias que precisam ser corrigidos"
            )

            exibir_tabela_validacao(
                erros_sobreaviso_df
            )

        else:
            st.success(
                "Nenhum médico possui mais de 24 horas de "
                "sobreaviso no mesmo dia."
            )