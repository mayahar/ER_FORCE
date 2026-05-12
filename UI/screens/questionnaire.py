import streamlit as st


def render(controller):
    st.markdown("""
    <style>
    .stApp {
        background-color: #001122;
        color: white;
        font-family: 'Courier New', monospace;
    }

    body {
        direction: rtl;
    }

    [data-testid="stSlider"] {
        direction: ltr !important;
        margin: 20px auto !important;
    }

    * {
        color: white !important;
    }

    [data-testid="stSlider"] label {
        color: #66aaff !important;
        font-size: 1.8em !important;
        font-weight: bold !important;
        text-align: center !important;
        display: block !important;
        width: 100% !important;
        text-shadow: 0 0 10px #66aaff !important;
        margin-bottom: 15px !important;
        direction: rtl !important;
    }

    [data-testid="stSlider"] .stSlider {
        width: 100% !important;
    }

    .stButton {
        position: fixed;
        bottom: 20px;
        left: 20px;
        z-index: 100;
        width: auto;
        display: inline-flex;
    }
    .stButton > button {
        background-color: #0066cc;
        color: white;
        border: none;
        border-radius: 5px;
        font-weight: bold;
        box-shadow: 0 0 10px #0066cc;
        padding: 10px 20px;
        font-size: 1.2em;
        width: auto;
    }
    .stButton > button:hover {
        background-color: #004499;
        box-shadow: 0 0 20px #0066cc;
    }

    h1 {
        color: #66aaff;
        text-shadow: 0 0 10px #66aaff;
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)

    st.title("Pre-game questionnaire")

    col1, col2, col3 = st.columns([0.1, 0.8, 0.1])
    research_context = st.session_state.state.get("research_context")

    with col2:
        fatigue = st.slider("Fatigue level", 0, 10, 5)
        st.write("")

        if research_context:
            sleep_last = research_context.get("sleep_last", 0)
            sleep_previous = research_context.get("sleep_previous", 0)
            st.info(
                f"Research day {research_context['day_number']}: "
                f"{research_context['condition']} | "
                f"sleep_last={sleep_last}, sleep_previous={sleep_previous}"
            )
        else:
            sleep_last = st.slider("Sleep hours last night", 0, 8, 6)
            st.write("")
            sleep_previous = st.slider("Sleep hours previous night", 0, 8, 6)

    if st.button("Continue"):
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
