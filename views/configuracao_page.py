import pandas as pd
import streamlit as st

from auxiliar.google_sheets import (
    get_sheet_data,
    set_sheet_data,
)


BASES_DISPONIVEIS = {
    "Médicos": {
        "aba": "lista_medicos",
        "descricao": "Cadastro dos médicos e valores mínimos.",
    },
    "Exames": {
        "aba": "lista_exames",
        "descricao": "Cadastro dos exames e respectivos valores.",
    },
    "Base de dados": {
        "aba": "base_dados",
        "descricao": "Registros dos atendimentos realizados.",
    },
    "Outros valores": {
        "aba": "outros_valores",
        "descricao": "Configuração de taxas e outros valores do sistema.",
    },
}


def limpar_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    Remove linhas totalmente vazias e substitui valores NaN por texto vazio.
    """
    dataframe = dataframe.copy()

    dataframe.columns = [
        str(coluna).strip()
        for coluna in dataframe.columns
    ]

    # Identifica linhas que possuem pelo menos um valor preenchido.
    linhas_preenchidas = dataframe.apply(
        lambda linha: any(
            pd.notna(valor) and str(valor).strip() != ""
            for valor in linha
        ),
        axis=1,
    )

    dataframe = dataframe.loc[linhas_preenchidas].copy()

    # Evita enviar NaN para o Google Sheets.
    dataframe = dataframe.where(
        pd.notna(dataframe),
        "",
    )

    return dataframe.reset_index(drop=True)


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

configuracao_base = BASES_DISPONIVEIS[base_selecionada]

nome_aba = configuracao_base["aba"]
descricao_base = configuracao_base["descricao"]


st.info(descricao_base)


# ============================================================
# Carregamento da planilha
# ============================================================

try:
    with st.spinner("Carregando dados da planilha..."):
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
    "linhas. As alterações só serão enviadas ao Google Sheets "
    "quando você clicar em salvar."
)


dataframe_editado = st.data_editor(
    dataframe_original,
    use_container_width=True,
    hide_index=True,
    num_rows="dynamic",
    key=f"editor_configuracao_{nome_aba}",
)


quantidade_original = len(dataframe_original)
quantidade_editada = len(
    limpar_dataframe(dataframe_editado)
)


coluna_registros, coluna_aba = st.columns(2)

with coluna_registros:
    st.metric(
        "Quantidade de registros",
        quantidade_editada,
        delta=quantidade_editada - quantidade_original,
    )

with coluna_aba:
    st.metric(
        "Aba selecionada",
        nome_aba,
    )


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
    dataframe_para_salvar = limpar_dataframe(
        dataframe_editado
    )

    try:
        with st.spinner("Salvando alterações..."):
            set_sheet_data(
                nome_aba,
                dataframe_para_salvar,
            )

        st.session_state[
            "mensagem_configuracao_salva"
        ] = (
            f"As alterações da base “{base_selecionada}” "
            "foram salvas com sucesso."
        )

        st.rerun()

    except Exception as error:
        st.error(
            f"Não foi possível salvar as alterações "
            f"na aba `{nome_aba}`."
        )
        st.exception(error)