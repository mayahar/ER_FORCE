import streamlit as st


BACKGROUND = "#001122"
SURFACE = "#002244"
SURFACE_DARK = "#001a33"
BORDER = "#004466"
PRIMARY = "#0066cc"
PRIMARY_HOVER = "#004499"
ACCENT = "#66aaff"
TEXT = "white"
WARNING_BG = "#332200"
WARNING = "#ffcc66"
ERROR_BG = "#441111"
ERROR_BORDER = "#ff3333"
ERROR_TEXT = "#ff6666"
POSITIVE = "#84cc16"
NEGATIVE = "#ef4444"


BASE_THEME = f"""
.stApp {{
    background-color: {BACKGROUND};
    color: {TEXT};
    direction: rtl;
    font-family: 'Courier New', monospace;
}}
"""

HEADINGS = f"""
h1, h2, h3 {{
    color: {ACCENT};
    text-shadow: 0 0 10px {ACCENT};
    text-align: center;
}}
"""

PRIMARY_BUTTONS = f"""
.stButton > button,
.stDownloadButton > button {{
    background-color: {PRIMARY};
    color: {TEXT};
    border: none;
    border-radius: 6px;
    font-weight: bold;
    box-shadow: 0 0 10px {PRIMARY};
}}

.stButton > button:hover,
.stDownloadButton > button:hover {{
    background-color: {PRIMARY_HOVER};
    box-shadow: 0 0 20px {PRIMARY};
}}
"""

FIXED_CONTINUE_BUTTON = """
.stButton {
    position: fixed;
    bottom: 20px;
    left: 20px;
    z-index: 100;
    width: auto;
    display: inline-flex;
}
"""

FORM_INPUTS = f"""
.stTextInput label,
.stTextInput label p,
.stNumberInput label,
.stNumberInput label p,
div[data-testid="stTextInput"] label,
div[data-testid="stNumberInput"] label,
div[data-testid="stSelectbox"] label {{
    color: {TEXT} !important;
    font-size: 2em !important;
    font-weight: bold !important;
}}

.stTextInput > div > div > input,
.stNumberInput > div > div > input {{
    background-color: {SURFACE};
    color: {TEXT};
    border: 2px solid {BORDER};
    border-radius: 5px;
}}
"""

SLIDERS = f"""
body {{
    direction: rtl;
}}

[data-testid="stSlider"] {{
    direction: ltr !important;
    margin: 20px auto !important;
}}

* {{
    color: {TEXT} !important;
}}

[data-testid="stSlider"] label {{
    color: {ACCENT} !important;
    font-size: 1.8em !important;
    font-weight: bold !important;
    text-align: center !important;
    display: block !important;
    width: 100% !important;
    text-shadow: 0 0 10px {ACCENT} !important;
    margin-bottom: 15px !important;
    direction: rtl !important;
}}

[data-testid="stSlider"] .stSlider {{
    width: 100% !important;
}}
"""

STATUS_MESSAGES = f"""
div[data-testid="stInfo"] {{
    background-color: {SURFACE};
    color: {TEXT};
    border: 1px solid {PRIMARY};
}}

div[data-testid="stWarning"] {{
    background-color: {WARNING_BG};
    color: {WARNING};
}}

div[data-testid="stError"] {{
    background-color: {ERROR_BG};
    color: {ERROR_TEXT};
}}
"""


def apply_css(css):
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def apply_enter_id_theme():
    apply_css(
        BASE_THEME
        + HEADINGS
        + FORM_INPUTS
        + FIXED_CONTINUE_BUTTON
        + PRIMARY_BUTTONS
        + f"""
.error-box {{
    background-color: {ERROR_BG};
    border: 2px solid {ERROR_BORDER};
    color: {ERROR_TEXT};
    padding: 20px;
    border-radius: 5px;
    font-weight: bold;
    text-align: center;
    margin: 20px 0;
}}

.research-brand {{
    display: flex;
    direction: ltr;
    justify-content: flex-end;
    width: 100%;
    margin: 8px 0 28px;
}}

.research-brand__text {{
    direction: rtl;
    color: {ACCENT};
    border-right: 4px solid {ACCENT};
    padding: 10px 18px 10px 0;
    font-size: clamp(2rem, 4vw, 3.4rem);
    font-weight: 800;
    line-height: 1.05;
    text-align: right;
    text-shadow: 0 0 10px {ACCENT};
}}
"""
    )


def apply_questionnaire_theme():
    apply_css(
        BASE_THEME
        + HEADINGS
        + SLIDERS
        + FIXED_CONTINUE_BUTTON
        + PRIMARY_BUTTONS
        + """
.stButton > button {
    padding: 10px 20px;
    font-size: 1.2em;
    width: auto;
}
"""
    )


def apply_new_user_sleep_gate_theme():
    apply_css(BASE_THEME + HEADINGS + SLIDERS + FIXED_CONTINUE_BUTTON + PRIMARY_BUTTONS)


def apply_game_theme():
    apply_css(
        BASE_THEME
        + HEADINGS
        + PRIMARY_BUTTONS
        + STATUS_MESSAGES
        + f"""
h1 {{
    margin-bottom: 30px;
}}

.game-box {{
    background-color: {SURFACE};
    border: 2px solid {BORDER};
    border-radius: 12px;
    padding: 30px;
    margin-top: 20px;
    box-shadow: 0 0 15px rgba(0, 102, 204, 0.4);
}}

.warning-text {{
    color: {WARNING};
    font-size: 1.2em;
    font-weight: bold;
    margin-bottom: 20px;
    text-align: center;
    line-height: 1.8;
}}

.info-text {{
    color: {TEXT};
    font-size: 1.1em;
    text-align: center;
    line-height: 1.8;
}}

.stButton > button {{
    border-radius: 8px;
    padding: 12px 24px;
    font-size: 1.1em;
    width: 100%;
    transition: 0.3s;
}}
"""
    )


def apply_results_theme():
    apply_css(
        BASE_THEME
        + HEADINGS
        + PRIMARY_BUTTONS
        + f"""
.block-box {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    padding: 12px;
    border-radius: 8px;
    margin-bottom: 10px;
}}

.metric-box {{
    background-color: {SURFACE_DARK};
    border-radius: 12px;
    padding: 20px;
    text-align: center;
    margin-bottom: 20px;
}}
"""
    )


def apply_baseline_saved_theme():
    apply_css(
        BASE_THEME
        + HEADINGS
        + PRIMARY_BUTTONS
        + f"""
.baseline-box {{
    background-color: {SURFACE};
    border: 2px solid {PRIMARY};
    border-radius: 8px;
    padding: 28px;
    text-align: center;
    margin-top: 30px;
    font-size: 1.2em;
}}
"""
    )


def score_card_html(score, color):
    return f"""
    <div style="
        text-align:center;
        padding:25px;
        border-radius:20px;
        box-shadow: 0 0 30px {color};
        border: 2px solid {color};
        margin-bottom:20px;
    ">
        <h2>רמת עייפות</h2>
        <h1 style="color:{color}; font-size:60px;">
            {score:.2f}
        </h1>
    </div>
    """
