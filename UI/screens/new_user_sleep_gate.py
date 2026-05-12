import streamlit as st


def render(controller):
    st.markdown("""
    <style>
    .stApp {
        background-color: #001122;
        color: white;
        direction: rtl;
        font-family: 'Courier New', monospace;
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
    h1 {
        color: #66aaff;
        text-shadow: 0 0 10px #66aaff;
        text-align: center;
        /* Make slider LTR to fix interaction issues */
    [data-testid="stSlider"] {
        direction: ltr !important;
        margin: 20px auto !important;
    }
                
    /* Make slider LTR to fix interaction issues */
    [data-testid="stSlider"] {
        direction: ltr !important;
        margin: 20px auto !important;
    }
    
    /* Make all text visible and white */
    * {
        color: white !important;
    }
    
    /* Center slider labels only */
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
    
    /* Make slider track and thumb visible */
    [data-testid="stSlider"] .stSlider {
        width: 100% !important;
    }

    }
    </style>
    """, unsafe_allow_html=True)

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
