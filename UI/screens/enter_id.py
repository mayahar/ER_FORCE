import streamlit as st

def render(controller):

    st.title("Enter Subject ID")

    subject_id = st.text_input("Subject ID")

    if st.button("Continue"):
        controller.dispatch("ID_SUBMITTED", {"subject_id": subject_id})

        st.session_state.state["session_id"] = subject_id
        st.session_state.state["screen"] = "questionnaire"
        st.rerun()