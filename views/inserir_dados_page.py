import streamlit as st

from auxiliar.google_sheets import get_sheet_data


st.title("Lista de exames")

st.write("Dados cadastrados na planilha `lista_exames`.")


if st.button(
    "🔄 Atualizar dados",
    use_container_width=False,
):
    get_sheet_data.clear()
    st.rerun()


try:
    with st.spinner("Carregando dados da planilha..."):
        lista_exames_df = get_sheet_data("lista_exames")

except Exception as error:
    st.error(
        "Não foi possível carregar os dados da planilha."
    )
    st.error(str(error))
    st.stop()


if lista_exames_df.empty:
    st.info("A planilha `lista_exames` está vazia.")

else:
    st.metric(
        label="Quantidade de registros",
        value=len(lista_exames_df),
    )

    st.dataframe(
        lista_exames_df,
        use_container_width=True,
        hide_index=True,
    )