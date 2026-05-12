import streamlit as st
from styles import apply_questionnaire_theme


def render(controller):
    apply_questionnaire_theme()

    st.title("שאלון עייפות")

    col1, col2, col3 = st.columns([0.1, 0.8, 0.1])
    research_context = st.session_state.state.get("research_context")

    with col2:
        fatigue = st.slider("מה רמת עייפות שלך?", 0, 10, 5)
        st.write("")

        if research_context:
            sleep_last = research_context.get("sleep_last", 0)
            sleep_previous = research_context.get("sleep_previous", 0)
            st.info(
                f"יום מחקר {research_context['day_number']}: "
                f"שינה אתמול={sleep_last}, שינה שלשום={sleep_previous}"
            )
        else:
            sleep_last = st.slider("כמה שעות ישנת אתמול?", 0, 8, 6)
            st.write("")
            sleep_previous = st.slider("כמה שעות ישנת שלשום?", 0, 8, 6)

    if st.button("המשך"):
        questionnaire = {
            "fatigue_self": fatigue,
            "sleep_last": sleep_last,
            "sleep_previous": sleep_previous,
        }

        if research_context:
            questionnaire.update({
                "research_day": research_context["day_number"],
                "research_condition": research_context["condition"],
                "study_id": research_context["study_id"],
            })

        controller.dispatch("QUESTIONNAIRE_DONE", questionnaire)

        st.session_state.state["screen"] = "game"
        st.rerun()
