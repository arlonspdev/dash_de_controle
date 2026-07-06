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

pag_configuracao = st.Page(
    "views/configuracao_page.py",
    title="Configurar e Editar Bases de Dados",
    icon="⚙️",
)

pag_controle_financeiro = st.Page(
    "views/controle_financeiro_page.py",
    title="Controle Financeiro - Dia",
    icon="💰",
)

pag_controle_medico = st.Page(
    "views/controle_medico_page.py",
    title="Controle Financeiro - Médico",
    icon="🩺",
)

paginas = {
    "Inserir Dados": [
        pag_inserir_dados
    ],
    "Controle Financeiro": [
        pag_controle_financeiro,
        pag_controle_medico
    ],
    "Configurações": [
        pag_configuracao
    ]
}  

navegacao = st.navigation(paginas)
navegacao.run()