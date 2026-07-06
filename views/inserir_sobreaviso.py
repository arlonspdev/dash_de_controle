# ============================================================
# Período e resumo do valor
# ============================================================

tipo_sobreaviso = st.radio(
    "Período do sobreaviso",
    options=["12h", "24h"],
    horizontal=True,
)

multiplicador_sobreaviso = (
    2 if tipo_sobreaviso == "24h" else 1
)

valor_sobreaviso_final = (
    valor_sobreaviso * multiplicador_sobreaviso
)


with st.container(border=True):
    coluna_texto, coluna_valor = st.columns(
        [3, 1],
        vertical_alignment="center",
    )

    with coluna_texto:
        st.markdown(
            f"### Valor do sobreaviso {tipo_sobreaviso}"
        )

        st.caption(
            "Valor definido em Configurações → Outros valores. "
            "Para o período de 24h, o valor é multiplicado por 2."
        )

    with coluna_valor:
        st.metric(
            "Valor",
            formatar_moeda(valor_sobreaviso_final),
        )