import streamlit as st

st.set_page_config(
    page_title="Sistema de Exames",
    page_icon="📋",
    layout="wide",
)

pag_inserir_dados = st.Page(
    "views/inserir_dados_page.py",
    title="Inserir dados",
    icon="📋",
    default=True,
)

paginas = {
    "Inserir Dados": [
        pag_inserir_dados
    ],
}


navegacao = st.navigation(paginas)
navegacao.run()