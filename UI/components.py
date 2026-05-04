import streamlit as st

def title(text):
    st.title(text)

def subtitle(text):
    st.subheader(text)

def info(text):
    st.info(text)

def next_button(label="Next"):
    return st.button(label)

def progress(value):
    st.progress(value)