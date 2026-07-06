import streamlit as st

st.set_page_config(
    page_title="Hello Streamlit",
    page_icon="👋",
)

st.title("Hello, Streamlit! 👋")
st.write("Your Streamlit setup is working correctly.")

if st.button("Test button"):
    st.success("Everything is working!")