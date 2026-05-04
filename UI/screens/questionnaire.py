import streamlit as st

def render(controller):

    st.title("Questionnaire")

    fatigue = st.slider("Subjective fatigue", 1, 10, 5)
    sleep_last = st.slider("Sleep last night", 0, 12, 6)
    sleep_prev = st.slider("Sleep previous night", 0, 12, 6)

    if st.button("Continue"):

        controller.dispatch("QUESTIONNAIRE_DONE", {
            "fatigue_self": fatigue,
            "sleep_last": sleep_last,
            "sleep_prev": sleep_prev
        })

        st.session_state.state["screen"] = "game"
        st.rerun()