import streamlit as st
from styles import apply_enter_id_theme
from core.research_repository import (
    get_current_research_day,
    get_research_participant,
    get_research_participant_ids,
    is_research_enabled,
)
from core.subject_repository import (
    create_or_update_subject_profile,
    create_subject,
    get_all_subject_ids,
    subject_exists,
)


EXISTING_USER_MODE = "בדיקת עייפות למשתמש קיים"
NEW_USER_MODE = "הזן משתמש חדש"

SEX_OPTIONS = {
    "זכר": "male",
    "נקבה": "female",
    "אחר": "other",
}


def render(controller):
    apply_enter_id_theme()

    # Inject custom CSS to make radio button labels and options white
    st.markdown(
        """
        <style>
        div[data-testid='stRadio'] label, div[data-testid='stRadio'] p {
            color: white !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("התחלת משחק")

    if is_research_enabled():
        research_day = get_current_research_day()
        participant_ids = get_research_participant_ids()

        st.markdown(
            '<div class="research-brand"><div class="research-brand__text">מתים מעייפות</div></div>',
            unsafe_allow_html=True,
        )

        if not research_day:
            st.error("מחקר לא זמין כרגע. אנא בדוק שוב מאוחר יותר.")
            return

        if not participant_ids:
            st.error("לא הגודרו משתתפים במחקר. אנא פנה למנהל המחקר.")
            return

        subject_id = st.selectbox("בחר/י מספר אישי", participant_ids)

        st.info(
            f"יום המחקר: {research_day['day_number']} "
        )

        if st.button("המשך"):
            participant = get_research_participant(subject_id)

            if not participant:
                st.error("Selected participant is missing from the research configuration.")
                return

            create_or_update_subject_profile(
                subject_id,
                name=participant.get("name"),
                sex=participant.get("sex", "unknown"),
                age=participant.get("age", 0),
            )

            if controller.load_subject(subject_id):
                controller.dispatch("ID_SUBMITTED", {"subject_id": subject_id})
                st.session_state.result = None
                st.session_state.state["session_id"] = subject_id
                st.session_state.state["research_context"] = research_day
                st.session_state.state["baseline_capture"] = research_day["is_baseline_day"]
                st.session_state.state["screen"] = "questionnaire"
                st.rerun()

        return

    available_ids = get_all_subject_ids()

    mode = st.radio(
        "בחר פעולה",
        [EXISTING_USER_MODE, NEW_USER_MODE],
        horizontal=True,
    )

    subject_id = st.text_input("הזן מס' אישי")

    name = None
    sex = "unknown"
    age = 0

    if mode == NEW_USER_MODE:
        name = st.text_input("שם מלא")
        sex_label = st.selectbox("מין", list(SEX_OPTIONS.keys()))
        sex = SEX_OPTIONS[sex_label]
        age = st.number_input("גיל", min_value=1, max_value=120, value=18, step=1)

    if st.button("המשך"):
        if not subject_id or not subject_id.strip():
            st.error("אנא הזן מזהה תקני")
            return

        if mode == EXISTING_USER_MODE and not subject_exists(subject_id):
            st.error(f"שגיאה: מזהה {subject_id} לא קיים במסד הנתונים")
            st.error(f"מזהים זמינים: {', '.join(map(str, available_ids))}")
            return

        if mode == NEW_USER_MODE:
            if subject_exists(subject_id):
                st.error("המשתמש כבר קיים. בחר 'בדיקת עייפות למשתמש קיים' כדי להמשיך.")
                return

            if not name or not name.strip():
                st.error("אנא הזן שם מלא")
                return

            try:
                create_subject(subject_id, name=name, sex=sex, age=age)
            except (ValueError, TypeError):
                st.error("מס' אישי וגיל חייבים להיות מספריים תקינים")
                return

        if controller.load_subject(subject_id):
            controller.dispatch("ID_SUBMITTED", {"subject_id": subject_id})
            st.session_state.result = None
            st.session_state.state["session_id"] = subject_id
            st.session_state.state.pop("research_context", None)
            st.session_state.state["baseline_capture"] = mode == NEW_USER_MODE
            st.session_state.state["screen"] = (
                "new_user_sleep_gate" if mode == NEW_USER_MODE else "questionnaire"
            )
            st.rerun()
