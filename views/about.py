from datetime import date

import streamlit as st


NOME_APP = "ARLONSP - SERVIÇOS MÉDICOS"
DATA_ULTIMA_ATUALIZACAO = date(2026, 8, 12)


def formatar_data_brasileira(data: date) -> str:
    """
    Formata uma data no padrão brasileiro.
    """
    return data.strftime("%d/%m/%Y")


# ============================================================
# Cabeçalho
# ============================================================

with st.container(border=True):
    coluna_icone, coluna_titulo = st.columns(
        [1, 8],
        vertical_alignment="center",
    )

    with coluna_icone:
        st.markdown("# ℹ️")

    with coluna_titulo:
        st.title("Sobre o app")

        st.caption(
            "Informações gerais sobre o sistema."
        )


# ============================================================
# Conteúdo
# ============================================================

with st.container(border=True):
    st.markdown(
        f"## {NOME_APP}"
    )

    st.markdown(
        "Este aplicativo foi desenvolvido para auxiliar no "
        "registro, consulta e controle financeiro dos atendimentos "
        "realizados pela ARLONSP."
    )

    st.markdown(
        "O sistema permite cadastrar atendimentos, exames, "
        "procedimentos, convênios, médicos, sobreavisos, marcações "
        "de meio período e gerar relatórios para conferência."
    )

    st.divider()

    coluna_versao, coluna_data = st.columns(2)

    with coluna_versao:
        st.metric(
            "Versão",
            "1.0",
        )

    with coluna_data:
        st.metric(
            "Última atualização",
            formatar_data_brasileira(
                DATA_ULTIMA_ATUALIZACAO
            ),
        )


with st.container(border=True):
    st.markdown("### Observações")

    st.info(
        "Não há observações no momento."
    )

