import streamlit as st

def render(controller):

    st.title("Game Running")

    st.write("Game + eye tracking + voice recording running in parallel")

    if st.button("Start Session"):

        controller.dispatch("GAME_STARTED")

        with st.spinner("Running multimodal session..."):

            controller.run_multimodal_game()

        controller.dispatch("GAME_DONE")

        st.session_state.state["screen"] = "result"
        st.rerun()