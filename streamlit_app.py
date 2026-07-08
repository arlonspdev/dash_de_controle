import hmac

import streamlit as st


st.set_page_config(
    page_title="Sistema de Exames",
    page_icon="📋",
    layout="wide",
)


# ============================================================
# Funções de login
# ============================================================

def validar_login(
    usuario_digitado: str,
    senha_digitada: str,
) -> bool:
    """
    Compara o usuário e a senha digitados com os valores
    armazenados no Streamlit Secrets.
    """
    try:
        usuario_correto = str(
            st.secrets["login"]["usuario"]
        )

        senha_correta = str(
            st.secrets["login"]["senha"]
        )

    except KeyError:
        st.error(
            "As credenciais de login não foram configuradas "
            "corretamente no Streamlit Secrets."
        )
        return False

    usuario_valido = hmac.compare_digest(
        usuario_digitado.strip(),
        usuario_correto,
    )

    senha_valida = hmac.compare_digest(
        senha_digitada,
        senha_correta,
    )

    return usuario_valido and senha_valida


def exibir_pagina_login() -> None:
    """
    Exibe o formulário de login.
    """
    coluna_esquerda, coluna_login, coluna_direita = st.columns(
        [1, 1.2, 1]
    )

    with coluna_login:
        with st.container(border=True):
            st.markdown(
                """
                <div style="text-align: center;">
                    <div style="font-size: 55px;">🩺</div>
                    <h2 style="margin-bottom: 0;">
                        ARLONSP
                    </h2>
                    <p style="margin-top: 0;">
                        SERVIÇOS MÉDICOS
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.divider()

            with st.form("formulario_login"):
                usuario = st.text_input(
                    "Usuário",
                    placeholder="Digite seu usuário",
                )

                senha = st.text_input(
                    "Senha",
                    type="password",
                    placeholder="Digite sua senha",
                )

                entrar = st.form_submit_button(
                    "Entrar",
                    type="primary",
                    use_container_width=True,
                )

            if entrar:
                if validar_login(usuario, senha):
                    st.session_state["autenticado"] = True
                    st.session_state["usuario_logado"] = (
                        usuario.strip()
                    )

                    st.rerun()

                else:
                    st.error("Usuário ou senha incorretos.")


def fazer_logout() -> None:
    """
    Encerra a sessão atual.
    """
    st.session_state["autenticado"] = False
    st.session_state.pop("usuario_logado", None)

    st.rerun()


# ============================================================
# Verificação do login
# ============================================================

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False


if not st.session_state["autenticado"]:
    exibir_pagina_login()
    st.stop()


# ============================================================
# Informações do usuário na barra lateral
# ============================================================

with st.sidebar:
    st.markdown("### ARLONSP")

    st.caption(
        f"Usuário: "
        f"{st.session_state.get('usuario_logado', '')}"
    )

    if st.button(
        "🚪 Sair",
        use_container_width=True,
    ):
        fazer_logout()

    st.divider()


# ============================================================
# Páginas
# ============================================================

pag_inserir_dados = st.Page(
    "views/inserir_dados_page.py",
    title="Inserir Procedimentos e Exames",
    icon="📋",
    default=True,
)

pag_inserir_sobreaviso = st.Page(
    "views/inserir_sobreaviso.py",
    title="Inserir Sobreaviso",
    icon="📟",
)

pag_meio_periodo = st.Page(
    "views/meio_periodo_page.py",
    title="Definir Meio de Período",
    icon="⏱️",
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


# ============================================================
# Navegação
# ============================================================

paginas = {
    "Inserir Dados": [
        pag_inserir_dados,
        pag_inserir_sobreaviso,
        pag_meio_periodo,
    ],
    "Controle Financeiro": [
        pag_controle_financeiro,
        pag_controle_medico,
    ],
    "Configurações": [
        pag_configuracao,
    ],
}


navegacao = st.navigation(paginas)
navegacao.run()