import streamlit as st
import os
import sys
import subprocess
import time

# Path to the FlightGear session script
FG_SCRIPT_PATH = r"c:\Users\לינוי\Documents\ער FORCE\07-05-2026\sivaks_logging_version\logging_fg_start_ver5.py"


def _is_pid_running(pid: int) -> bool:
    if not pid:
        return False
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}"],
            text=True,
            stderr=subprocess.STDOUT,
        )
        return str(pid) in out
    except Exception:
        return False


def _start_flightgear_session() -> tuple[int, str]:
    if not os.path.exists(FG_SCRIPT_PATH):
        return 0, f"FlightGear script not found: {FG_SCRIPT_PATH}"

    script_dir = os.path.dirname(FG_SCRIPT_PATH)

    try:
        p = subprocess.Popen(
            [sys.executable, FG_SCRIPT_PATH],
            cwd=script_dir,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        return int(p.pid), ""

    except Exception as e:
        return 0, f"Failed to start FlightGear session: {e}"


def render(controller):

    # ===== Styling =====
    st.markdown("""
    <style>
    .stApp {
        background-color: #001122;
        color: white;
        direction: rtl;
        font-family: 'Courier New', monospace;
    }

    h1 {
        color: #66aaff;
        text-shadow: 0 0 10px #66aaff;
        text-align: center;
        margin-bottom: 30px;
    }

    .game-box {
        background-color: #002244;
        border: 2px solid #004466;
        border-radius: 12px;
        padding: 30px;
        margin-top: 20px;
        box-shadow: 0 0 15px rgba(0, 102, 204, 0.4);
    }

    .warning-text {
        color: #ffcc66;
        font-size: 1.2em;
        font-weight: bold;
        margin-bottom: 20px;
        text-align: center;
        line-height: 1.8;
    }

    .info-text {
        color: white;
        font-size: 1.1em;
        text-align: center;
        line-height: 1.8;
    }

    .stButton > button {
        background-color: #0066cc;
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: bold;
        padding: 12px 24px;
        font-size: 1.1em;
        width: 100%;
        box-shadow: 0 0 10px #0066cc;
        transition: 0.3s;
    }

    .stButton > button:hover {
        background-color: #004499;
        box-shadow: 0 0 20px #0066cc;
    }

    div[data-testid="stInfo"] {
        background-color: #002244;
        color: white;
        border: 1px solid #0066cc;
    }

    div[data-testid="stWarning"] {
        background-color: #332200;
        color: #ffcc66;
    }

    div[data-testid="stError"] {
        background-color: #441111;
        color: #ff6666;
    }
    </style>
    """, unsafe_allow_html=True)

    # ===== Title =====
    st.title("הרצת משחק")

    # ===== Content Box =====
    st.markdown("""
    <div class="game-box">

    <div class="warning-text">
    שימו לב! המטוס יתחיל במצב אף מטה,<br>
    צריך למשוך מייד את הסטיק כדי לא להתרסק
    </div>

    <div class="info-text">
    במהלך המשחק ימדדו תנועות העיניים שלכם<br>
    ובנוסף תתבקשו להשמיע קולות מסוימים
    </div>

    </div>
    """, unsafe_allow_html=True)

    # ===== Session State =====
    if "fg_pid" not in st.session_state:
        st.session_state.fg_pid = 0
        st.session_state.fg_started_at = None
        st.session_state.fg_finished_handled = False
        st.session_state.fg_last_error = ""

    fg_pid = int(st.session_state.fg_pid or 0)
    fg_running = _is_pid_running(fg_pid)

    # ===== Buttons =====
    col1, col2 = st.columns(2)

    with col1:
        start_clicked = st.button(
            "התחלת משחק",
            disabled=fg_running
        )

    with col2:
        stop_clicked = st.button(
            "סיום הרצת משחק",
            disabled=not fg_running
        )

    # ===== Start Session =====
    if start_clicked:
        pid, err = _start_flightgear_session()

        if err:
            st.session_state.fg_last_error = err

        else:
            st.session_state.fg_pid = pid
            st.session_state.fg_started_at = time.time()
            st.session_state.fg_finished_handled = False
            st.session_state.fg_last_error = ""
            st.rerun()

    # ===== Stop Session =====
    if stop_clicked and fg_pid:
        try:
            subprocess.check_call(
                ["taskkill", "/PID", str(fg_pid), "/T", "/F"]
            )

            st.session_state.fg_pid = 0
            st.session_state.fg_started_at = None
            st.session_state.fg_finished_handled = True

            st.session_state.result = None
            st.session_state.state["screen"] = "result"

            st.rerun()

        except Exception as e:
            st.session_state.fg_last_error = (
                f"Failed to stop session: {e}"
            )

    # ===== Error Display =====
    if st.session_state.fg_last_error:
        st.error(st.session_state.fg_last_error)

    # ===== Running Status =====
    if fg_running:

        started_at = st.session_state.fg_started_at

        runtime_s = (
            int(time.time() - started_at)
            if started_at else None
        )

        st.info(
            f"המשחק רץ כעת"
            + (
                f" • {runtime_s} שניות"
                if runtime_s is not None else ""
            )
        )

        # Live refresh
        time.sleep(1)
        st.rerun()

    elif fg_pid:

        if not st.session_state.get(
            "fg_finished_handled",
            False
        ):
            st.session_state.fg_finished_handled = True
            st.session_state.result = None
            st.session_state.state["screen"] = "result"
            st.rerun()

        st.warning("המשחק הסתיים")