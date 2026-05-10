import streamlit as st
from core.subject_repository import subject_exists, get_all_subject_ids, create_subject

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
    div[data-testid="stTextInput"] label {
        color: white !important;
        font-size: 2em !important;
        font-weight: bold !important;
    }
    .stTextInput > div > div > input {
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
    
    # Display available subject IDs
    available_ids = get_all_subject_ids()

    mode = st.radio(
        "בחר פעולה",
        ["ניסיון חדש", "הזן משתמש חדש"],
        horizontal=True,
    )

    subject_id = st.text_input("הזן מס' אישי")

    if st.button("המשך"):
        # Validate subject exists
        if not subject_id or not subject_id.strip():
            st.error("❌ אנא הזן מזהה תקני")
            return
        
        if mode == "ניסיון חדש" and not subject_exists(subject_id):
            st.error(f"❌ שגיאה: מזהה {subject_id} לא קיים במסד הנתונים")
            st.error(f"📋 מזהים זמינים: {', '.join(map(str, available_ids))}")
            return

        if mode == "הזן משתמש חדש":
            if subject_exists(subject_id):
                st.error("❌ המשתמש כבר קיים. בחר 'ניסיון חדש' כדי להמשיך.")
                return
            try:
                create_subject(subject_id)
            except (ValueError, TypeError):
                st.error("❌ מס' אישי חייב להיות מספרי")
                return
        
        # Load subject and proceed
        if controller.load_subject(subject_id):
            controller.dispatch("ID_SUBMITTED", {"subject_id": subject_id})
            st.session_state.state["session_id"] = subject_id
            st.session_state.state["screen"] = (
                "new_user_sleep_gate" if mode == "הזן משתמש חדש" else "questionnaire"
            )
            st.rerun()
