import ctypes
import streamlit as st
import os
import sys
import subprocess
import time
from pathlib import Path

import numpy as np
from eye_tracking_analysis.eye_tracker_recorder import EyeTrackerRecorder
from eye_tracking_analysis.eye_movement_analyzer import EyeMovementAnalyzer
from styles import apply_game_theme

# ER_FORCE repo root (this file: UI/screens/game.py)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_FG_DIR = _REPO_ROOT / "game" / "sivaks_logging_version"
_DEFAULT_FG_SCRIPT = _DEFAULT_FG_DIR / "logging_fg_start_ver5.py"

_eye_recorder: EyeTrackerRecorder | None = None
_eye_analyzer: EyeMovementAnalyzer | None = None


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


def _initialize_eye_tracking_session():
    global _eye_recorder, _eye_analyzer
    if _eye_recorder is None:
        _eye_recorder = EyeTrackerRecorder()
    if _eye_analyzer is None:
        _eye_analyzer = EyeMovementAnalyzer()


def _start_eye_tracking() -> tuple[bool, str]:
    _initialize_eye_tracking_session()

    if _eye_recorder is None:
        return False, "Eye tracker recorder is unavailable."

    found = _eye_recorder.find_and_select_eyetracker(auto_select_first=True)
    if not found:
        return False, "לא נמצא עוקב עיניים. המשחק ימשיך בלי הקלטת עיניים."

    started = _eye_recorder.start_recording()
    if not started:
        return False, "שגיאה בהפעלה של הקלטת תנועות העיניים."

    return True, ""


def _stop_eye_tracking() -> tuple[dict | None, str]:
    global _eye_recorder, _eye_analyzer
    if _eye_recorder is None or not _eye_recorder.is_recording:
        return None, ""

    stopped = _eye_recorder.stop_recording()
    if not stopped:
        return None, "שגיאה בהפסקת הקלטת תנועות העיניים."

    gaze_data = _eye_recorder.get_collected_data()
    if not gaze_data:
        return None, "לא נאספו נתוני עיניים."

    eye_x = []
    eye_y = []
    timestamps = []

    for sample in gaze_data:
        x = sample.left_x if sample.left_x is not None else sample.right_x
        y = sample.left_y if sample.left_y is not None else sample.right_y
        eye_x.append(np.nan if x is None else x)
        eye_y.append(np.nan if y is None else y)
        timestamps.append(sample.timestamp)

    timestamps = np.array(timestamps, dtype=float)
    if timestamps.size == 0:
        return None, "אין חיווי זמן תקני בנתוני העין."

    if np.nanmax(timestamps) > 1e5:
        timestamps = timestamps / 1_000_000
    timestamps = timestamps - timestamps[0]

    gaze_x = np.array(eye_x, dtype=float)
    gaze_y = np.array(eye_y, dtype=float)

    if _eye_analyzer is None:
        st.session_state.eye_tracking_active = False
        return None, "אנלייזר של תנועות עיניים אינו זמין."

    try:
        fixations, saccades, metrics = _eye_analyzer.analyze_gaze_data(
            gaze_x=gaze_x,
            gaze_y=gaze_y,
            timestamps=timestamps,
        )
    except Exception as e:
        return None, f"ניתוח תנועות העיניים נכשל: {e}"

    if metrics is None:
        return None, "לא ניתן לחשב מדדים מתנועות העיניים."

    features = {
        "fixation_duration": float(metrics.mean_fixation_duration),
        "fixation_count": int(metrics.num_fixations),
        "saccade_count": int(metrics.num_saccades),
        "analysis": {
            "total_duration": float(metrics.total_duration),
            "fixations_per_minute": float(metrics.fixations_per_minute),
            "saccades_per_minute": float(metrics.saccades_per_minute),
            "mean_fixation_duration": float(metrics.mean_fixation_duration),
            "mean_saccade_velocity": float(metrics.mean_saccade_velocity),
        }
    }

    st.session_state.eye_tracking_active = False
    return features, ""


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

    fg_pid = int(st.session_state.fg_pid or 0)
    fg_running = _is_pid_running(fg_pid)

    # ===== Buttons =====
    col1, col2 = st.columns(2)
    stop_clicked = False

    with col1:
        start_clicked = st.button(
            "התחלת משחק",
            disabled=fg_running
        )

    if fg_running:
        with col2:
            stop_clicked = st.button("סיום הרצת משחק")

    # ===== Start Session =====
    if start_clicked:
        st.session_state.eye_features = None
        st.session_state.eye_recording_error = ""
        st.session_state.eye_tracking_active = False

        eye_started, eye_err = _start_eye_tracking()
        if eye_err:
            st.session_state.eye_recording_error = eye_err

        elif eye_started:
            st.session_state.eye_tracking_active = True

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
        eye_features, eye_err = _stop_eye_tracking()
        st.session_state.eye_tracking_active = False
        if eye_features:
            st.session_state.eye_features = eye_features
        if eye_err:
            st.session_state.eye_recording_error = eye_err

        ok, err = _terminate_session_process(fg_pid)
        if ok:
            st.session_state.fg_pid = 0
            st.session_state.fg_started_at = None
            st.session_state.fg_finished_handled = True
            st.session_state.fg_last_error = ""
            st.session_state.result = None
            st.session_state.state["screen"] = "result"
            st.rerun()
        else:
            st.session_state.fg_last_error = f"Failed to stop session: {err}"

    # ===== Error Display =====
    if st.session_state.fg_last_error:
        st.error(st.session_state.fg_last_error)

    if st.session_state.get("eye_recording_error"):
        st.warning(st.session_state.eye_recording_error)

    if st.session_state.get("eye_tracking_active"):
        st.info("הקלטת תנועות עיניים פעילה")

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
                eye_features, eye_err = _stop_eye_tracking()
                st.session_state.eye_tracking_active = False
                if eye_features:
                    st.session_state.eye_features = eye_features
                if eye_err:
                    st.session_state.eye_recording_error = eye_err

                st.session_state.result = None
                st.session_state.state["screen"] = "result"
                st.session_state.fg_pid = 0
                st.session_state.fg_started_at = None
            st.session_state.fg_finished_handled = True
            st.rerun()

        # Recovery: older builds left fg_pid set with fg_finished_handled; unstick → results.
        if st.session_state.fg_pid and st.session_state.get("fg_finished_handled"):
            st.session_state.fg_pid = 0
            st.session_state.fg_started_at = None
            st.session_state.result = None
            st.session_state.state["screen"] = "result"
            st.rerun()
