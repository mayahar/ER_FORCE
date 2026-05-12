import streamlit as st
from styles import apply_new_user_sleep_gate_theme


def render(controller):
    apply_new_user_sleep_gate_theme()

    st.title("בדיקת ערנות למשתמש חדש")
    # Create centered layout with columns
    col1, col2, col3 = st.columns([0.1, 0.8, 0.1])
    
    with col2:

        sleep_last = st.slider("שעות שינה אתמול", 0, 8, 7)
        st.write("")  # Spacing
        sleep_previous = st.slider("שעות שינה שלשום", 0, 8, 7)

    if st.button("המשך"):
        if sleep_last >= 7 and sleep_previous >= 7:
            st.session_state.state["baseline_capture"] = True
            st.session_state.state["screen"] = "game"
            st.rerun()

        st.error("אתה לא עומד בתנאי ערנות כדי להגדיר מצב בייסליין")
