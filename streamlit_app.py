import streamlit as st


st.set_page_config(
    page_title="Sistema de Exames",
    page_icon="📋",
    layout="wide",
)


def pagina_inicial():
    st.title("Sistema de Exames")

    st.write(
        """
        Bem-vindo ao sistema.

        Utilize o menu lateral para acessar as páginas disponíveis.
        """
    )


paginas = {
    "Principal": [
        st.Page(
            pagina_inicial,
            title="Início",
            icon="🏠",
            default=True,
        ),
    ],
    "Dados": [
        st.Page(
            "views/inserir_dados_page.py",
            title="Inserir dados",
            icon="📋",
        ),
    ],
}


navegacao = st.navigation(paginas)
navegacao.run()