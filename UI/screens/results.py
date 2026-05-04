import streamlit as st

def render(controller):

    st.title("Fatigue Result")

    result = controller.get_result()

    st.metric("Fatigue Score", result["score"])

    st.write("Breakdown")
    st.json(result["breakdown"])

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Restart"):
            controller.dispatch("RESET")
            st.session_state.state["screen"] = "enter_id"
            st.rerun()

    with col2:
        st.download_button(
            "Export Session",
            data=str(result),
            file_name="session.json"
        )