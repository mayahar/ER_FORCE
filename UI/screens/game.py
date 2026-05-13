import ctypes
import streamlit as st
import os
import sys
import subprocess
import time
from pathlib import Path
from styles import apply_game_theme
from core.voice.session import VoiceSessionManager, VoiceSessionError

# ER_FORCE repo root (this file: UI/screens/game.py)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_FG_DIR = _REPO_ROOT / "game" / "sivaks_logging_version"
_DEFAULT_FG_SCRIPT = _DEFAULT_FG_DIR / "logging_fg_start_ver5.py"


def _resolve_fg_script_path() -> Path | None:
    env = (os.environ.get("ER_FORCE_FG_SCRIPT") or os.environ.get("SIVAKS_LOGGING_FG_SCRIPT") or "").strip()
    if env:
        p = Path(env).expanduser()
        # Anchor relative paths to repo root first (avoids cwd under sivaks_logging_version
        # producing .../sivaks_logging_version/game/sivaks_logging_version/...).
        if not p.is_absolute():
            from_repo = (_REPO_ROOT / p).resolve()
            if from_repo.is_file():
                return from_repo
            cwd_resolved = p.resolve()
            if cwd_resolved.is_file():
                return cwd_resolved
            return None
        p = p.resolve()
        if p.is_file():
            return p
        return None
    if _DEFAULT_FG_SCRIPT.is_file():
        return _DEFAULT_FG_SCRIPT.resolve()
    return None


def _terminate_session_process(pid: int) -> tuple[bool, str]:
    if pid <= 0:
        return True, ""
    if sys.platform == "win32":
        r = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            return True, ""
        # 128: process not found — often the session already ended (user closed FG).
        combined = ((r.stdout or "") + (r.stderr or "")).lower()
        if r.returncode == 128 or "not found" in combined or "not running" in combined:
            return True, ""
        return False, (r.stderr or r.stdout or f"taskkill exited {r.returncode}").strip()
    try:
        os.kill(pid, 9)
        return True, ""
    except OSError:
        return True, ""


def _is_pid_running(pid: int) -> bool:
    """Windows: OpenProcess is reliable; tasklist /FI can fail (locale, CSV, timing)."""
    if pid <= 0:
        return False
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
    if h:
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    return False


def _start_flightgear_session() -> tuple[int, str]:
    script_path = _resolve_fg_script_path()
    if script_path is None:
        return 0, (
            f"FlightGear script not found. Expected: {_DEFAULT_FG_SCRIPT} "
            "or set ER_FORCE_FG_SCRIPT to logging_fg_start_ver5.py"
        )

    script_dir = str(script_path.parent)

    try:
        # Mark "this run" for the Streamlit process so results can read the correct session.
        os.environ["SIVAKS_FG_MIN_START_TS"] = str(time.time())
        # Session CSV / final_score.txt land under sivaks_logging_version/runs
        runs_root = str(Path(script_dir) / "runs")
        os.environ["SIVAKS_FG_RUNS_ROOT"] = runs_root
        # FlightGear: start fullscreen when launched from this UI (see logging_fg_start_ver5.py).
        os.environ["SIVAKS_FG_FULLSCREEN"] = "1"

        p = subprocess.Popen(
            [sys.executable, str(script_path.resolve())],
            cwd=script_dir,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        pid = int(p.pid)
        time.sleep(0.4)
        if not _is_pid_running(pid):
            return (
                0,
                "המשגר נסגר מיד — הרץ בטרמינל: "
                f'python "{script_path}" (מתוך {script_dir}) כדי לראות את השגיאה.',
            )
        return pid, ""

    except Exception as e:
        return 0, f"Failed to start FlightGear session: {e}"


def _create_voice_session(controller):
    subject_id = None
    if controller is not None and getattr(controller, "subject", None) is not None:
        subject_id = controller.subject.get("id")

    manager = VoiceSessionManager(subject_id=subject_id)
    manager.start_session()
    return manager


def _finalize_voice_session(controller):
    manager = st.session_state.pop("voice_session", None)
    if manager is None:
        return

    try:
        voice_data = manager.finalize_session()
        if controller is not None:
            controller.attach_voice_session_result(voice_data)
    except VoiceSessionError as exc:
        if controller is not None:
            controller.attach_voice_session_result({
                "session_id": manager.session_id,
                "subject_id": manager.subject_id,
                "started_at": manager.start_timestamp,
                "finished_at": manager.finish_timestamp,
                "events": [],
                "summary": {
                    "dLPC": 0.0,
                    "PARCOR": 0.0,
                    "LPC": 0.0,
                    "Pitch": 0.0,
                    "MFCC": 0.0,
                },
                "error": str(exc),
            })


def render(controller):

    apply_game_theme()

    # ===== Title =====
    st.title("הרצת משחק")

    # ===== Content Box =====
    st.markdown("""
    <div class="game-box">

    <div class="warning-text">
    שימו לב! המטוס יתחיל במצב אף מטה,<br>
    צריך למשוך מיד את הסטיק כדי לא להתרסק
    </div>

    <div class="info-text">
    למשחק יקח כחצי דקה להטען, בהתחלה יופיע מסלול המראה, ואז הוא יתחיל אוטומטית.<br>
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
        st.session_state.voice_only_running = False

    fg_pid = int(st.session_state.fg_pid or 0)
    fg_running = _is_pid_running(fg_pid)
    voice_only_running = bool(st.session_state.voice_only_running)

    # ===== Buttons =====
    audio_only_mode = st.checkbox(
        "הרצה עם אודיו בלבד (ללא פתיחת המשחק)",
        value=True,
    )

    col1, col2 = st.columns(2)
    stop_clicked = False

    with col1:
        start_clicked = st.button(
            "התחלת אודיו בלבד" if audio_only_mode else "התחלת משחק",
            disabled=fg_running or voice_only_running,
        )

    if fg_running or voice_only_running:
        with col2:
            stop_clicked = st.button(
                "סיום הרצת משחק" if fg_running else "סיום הפעלת אודיו",
            )

    # ===== Start Session =====
    if start_clicked:
        if audio_only_mode:
            st.session_state.voice_session = _create_voice_session(controller)
            st.session_state.voice_only_running = True
            st.session_state.fg_started_at = time.time()
            st.session_state.fg_last_error = ""
            st.rerun()
        else:
            pid, err = _start_flightgear_session()

            if err:
                st.session_state.fg_last_error = err

            else:
                st.session_state.fg_pid = pid
                st.session_state.fg_started_at = time.time()
                st.session_state.fg_finished_handled = False
                st.session_state.fg_last_error = ""
                st.session_state.voice_session = _create_voice_session(controller)
                st.rerun()

    # ===== Stop Session =====
    if stop_clicked:
        if fg_pid:
            ok, err = _terminate_session_process(fg_pid)
            if ok:
                st.session_state.fg_pid = 0
                st.session_state.fg_started_at = None
                st.session_state.fg_finished_handled = True
                st.session_state.fg_last_error = ""
                _finalize_voice_session(controller)
                st.session_state.voice_only_running = False
                st.session_state.result = None
                st.session_state.state["screen"] = "result"
                st.rerun()
            else:
                st.session_state.fg_last_error = f"Failed to stop session: {err}"
        elif voice_only_running:
            st.session_state.voice_only_running = False
            _finalize_voice_session(controller)
            st.session_state.result = None
            st.session_state.state["screen"] = "result"
            st.rerun()

    # ===== Error Display =====
    if st.session_state.fg_last_error:
        st.error(st.session_state.fg_last_error)

    # ===== Running Status =====
    if fg_running or voice_only_running:
        if st.session_state.get("voice_session") is not None:
            elapsed = time.time() - float(st.session_state.fg_started_at or time.time())
            try:
                st.session_state.voice_session.update(elapsed)
            except Exception as exc:
                st.session_state.fg_last_error = f"Voice session update failed: {exc}"

        started_at = st.session_state.fg_started_at

        runtime_s = (
            int(time.time() - started_at)
            if started_at else None
        )

        session_text = (
            "הרצת אודיו בלבד פעילה" if voice_only_running else "המשחק רץ כעת"
        )

        st.info(
            f"{session_text}"
            + (
                f" • {runtime_s} שניות"
                if runtime_s is not None else ""
            )
        )

        voice_session = st.session_state.get("voice_session")
        if voice_session is not None:
            prompt_text = voice_session.current_prompt
            completed_count = len(voice_session.completed_events)
            pending_count = len(voice_session.pending_events)
            failed_events = voice_session.failed_events
            st.markdown(
                f"**Voice recording status:** {prompt_text or 'No scheduled prompt yet.'}"
            )
            st.markdown(
                f"Completed voice events: {completed_count} • Pending: {pending_count}"
            )
            if failed_events:
                st.warning(
                    f"Failed voice events: {len(failed_events)}. "
                    f"Last error: {failed_events[-1].error or 'unknown'}"
                )
            else:
                active = voice_session.active_event
                if active is not None:
                    tts_error = active.metadata.get("tts_error")
                    if tts_error:
                        st.warning(f"TTS warning: {tts_error}")

        # Live refresh
        time.sleep(1)
        st.rerun()

    elif fg_pid:

        if not st.session_state.get(
            "fg_finished_handled",
            False
        ):
            started_at = st.session_state.fg_started_at
            elapsed = (time.time() - float(started_at)) if started_at else 999.0
            # Launcher + FG can take >3s to appear; treat very fast exit as error.
            if elapsed < 8.0:
                st.session_state.fg_last_error = (
                    "המשגר יצא מהר מדי — בדוק: game/sivaks_logging_version + "
                    "Aircraft/f16, נתיב FlightGear (yan/FlightGear_2020_3 או SIVAKS_FG_ROOT), "
                    "והרץ logging_fg_start_ver5.py מהטרמינל לראות שגיאה."
                )
                st.session_state.fg_pid = 0
                st.session_state.fg_started_at = None
            else:
                # Normal exit (user closed FlightGear or session finished): always go to results.
                # final_score.txt may be missing if FG was killed mid-run; result screen still runs
                # the pipeline with a fallback game score.
                _finalize_voice_session(controller)
                st.session_state.result = None
                st.session_state.state["screen"] = "result"
                st.session_state.fg_pid = 0
                st.session_state.fg_started_at = None
            st.session_state.fg_finished_handled = True
            st.rerun()

        # Recovery: older builds left fg_pid set with fg_finished_handled; unstick → results.
        if st.session_state.fg_pid and st.session_state.get("fg_finished_handled"):
            _finalize_voice_session(controller)
            st.session_state.fg_pid = 0
            st.session_state.fg_started_at = None
            st.session_state.result = None
            st.session_state.state["screen"] = "result"
            st.rerun()
