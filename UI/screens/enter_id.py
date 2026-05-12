import streamlit as st
from core.subject_repository import subject_exists, get_all_subject_ids, create_subject


EXISTING_USER_MODE = "בדיקת עייפות למשתמש קיים"
NEW_USER_MODE = "הזן משתמש חדש"

SEX_OPTIONS = {
    "זכר": "male",
    "נקבה": "female",
    "אחר": "other",
}


def render(controller):
    # Add Air Force inspired styling with dark blue theme
    st.markdown("""
    <style>
    .stApp {
        background-color: #001122;
        color: white;
        direction: rtl;
        font-family: 'Courier New', monospace;
    }
    .stTextInput label,
    .stTextInput label p,
    .stNumberInput label,
    .stNumberInput label p,
    div[data-testid="stTextInput"] label,
    div[data-testid="stNumberInput"] label,
    div[data-testid="stSelectbox"] label {
        color: white !important;
        font-size: 2em !important;
        font-weight: bold !important;
    }
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input {
        background-color: #002244;
        color: white;
        border: 2px solid #004466;
        border-radius: 5px;
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
    .error-box {
        background-color: #441111;
        border: 2px solid #ff3333;
        color: #ff6666;
        padding: 20px;
        border-radius: 5px;
        font-weight: bold;
        text-align: center;
        margin: 20px 0;
    }
    </style>
    """, unsafe_allow_html=True)

    st.title("התחלת משחק")

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
            st.session_state.state["session_id"] = subject_id
            st.session_state.state["baseline_capture"] = mode == NEW_USER_MODE
            st.session_state.state["screen"] = (
                "new_user_sleep_gate" if mode == NEW_USER_MODE else "questionnaire"
            )
            st.rerun()
