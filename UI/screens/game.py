import streamlit as st
import os
import sys
import subprocess
import time

FG_SCRIPT_PATH = r"C:\Users\srule\OneDrive\Desktop\yan\FlightGear_2020_3\sivaks_logging_version\logging_fg_start_ver5.py"


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

    st.title("Game Running")

    st.write("Game + eye tracking + voice recording running in parallel")

    if "fg_pid" not in st.session_state:
        st.session_state.fg_pid = 0
        st.session_state.fg_started_at = None
        st.session_state.fg_finished_handled = False
        st.session_state.fg_last_error = ""

    fg_pid = int(st.session_state.fg_pid or 0)
    fg_running = _is_pid_running(fg_pid)

    cols = st.columns([1, 1, 2])
    with cols[0]:
        start_clicked = st.button("Start Session", disabled=fg_running)
    with cols[1]:
        stop_clicked = st.button("Stop Session", disabled=not fg_running)

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

    if stop_clicked and fg_pid:
        try:
            subprocess.check_call(["taskkill", "/PID", str(fg_pid), "/T", "/F"])
            st.session_state.fg_pid = 0
            st.session_state.fg_started_at = None
            st.session_state.fg_finished_handled = True
            st.session_state.result = None
            st.session_state.state["screen"] = "result"
            st.rerun()
        except Exception as e:
            st.session_state.fg_last_error = f"Failed to stop session: {e}"

    if st.session_state.fg_last_error:
        st.error(st.session_state.fg_last_error)

    if fg_running:
        started_at = st.session_state.fg_started_at
        runtime_s = int(time.time() - started_at) if started_at else None
        st.info(
            f"Session running (PID {fg_pid})"
            + (f" • {runtime_s}s" if runtime_s is not None else "")
        )
        # Streamlit doesn't update unless we trigger reruns.
        # Keep the timer live by rerunning once per second while the session is active.
        time.sleep(1)
        st.rerun()
    elif fg_pid:
        # Process finished -> route to result screen (no popups)
        if not st.session_state.get("fg_finished_handled", False):
            st.session_state.fg_finished_handled = True
            st.session_state.result = None
            st.session_state.state["screen"] = "result"
            st.rerun()

        st.warning(f"Last started PID {fg_pid} is not running anymore.")