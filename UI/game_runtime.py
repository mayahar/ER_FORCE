import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path

from voice.session import VoiceSessionError, VoiceSessionManager


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FG_DIR = REPO_ROOT / "game" / "sivaks_logging_version"
DEFAULT_FG_SCRIPT = DEFAULT_FG_DIR / "logging_fg_start_ver5.py"


def resolve_fg_script_path():
    env = (os.environ.get("ER_FORCE_FG_SCRIPT") or os.environ.get("SIVAKS_LOGGING_FG_SCRIPT") or "").strip()
    if env:
        candidate = Path(env).expanduser()
        if not candidate.is_absolute():
            from_repo = (REPO_ROOT / candidate).resolve()
            if from_repo.is_file():
                return from_repo
            cwd_resolved = candidate.resolve()
            return cwd_resolved if cwd_resolved.is_file() else None
        candidate = candidate.resolve()
        return candidate if candidate.is_file() else None

    return DEFAULT_FG_SCRIPT.resolve() if DEFAULT_FG_SCRIPT.is_file() else None


def terminate_session_process(pid):
    if pid <= 0:
        return True, ""

    if sys.platform == "win32":
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True, ""
        combined = ((result.stdout or "") + (result.stderr or "")).lower()
        if result.returncode == 128 or "not found" in combined or "not running" in combined:
            return True, ""
        return False, (result.stderr or result.stdout or f"taskkill exited {result.returncode}").strip()

    try:
        os.kill(pid, 9)
        return True, ""
    except OSError:
        return True, ""


def is_pid_running(pid):
    if pid <= 0:
        return False

    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    process_query_limited_information = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, 0, pid)
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    return False


def start_flightgear_session(controller=None):
    script_path = resolve_fg_script_path()
    if script_path is None:
        return 0, (
            f"FlightGear script not found. Expected {DEFAULT_FG_SCRIPT}, "
            "or set ER_FORCE_FG_SCRIPT to logging_fg_start_ver5.py."
        )

    script_dir = str(script_path.parent)

    try:
        if controller and getattr(controller, "session", None):
            runs_root = Path(controller.session.game_dir)
        else:
            runs_root = Path(script_dir) / "runs"

        runs_root.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["SIVAKS_FG_MIN_START_TS"] = str(time.time())
        env["SIVAKS_FG_RUNS_ROOT"] = str(runs_root.resolve())
        env["SIVAKS_FG_SESSION_DIR_IS_FINAL"] = "1" if controller and getattr(controller, "session", None) else "0"
        env["SIVAKS_FG_FULLSCREEN"] = "1"

        process = subprocess.Popen(
            [sys.executable, str(script_path.resolve())],
            cwd=script_dir,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        pid = int(process.pid)
        time.sleep(0.4)

        if not is_pid_running(pid):
            return (
                0,
                f'Launcher closed immediately. Run python "{script_path}" from {script_dir} to see the error.',
            )

        return pid, ""
    except Exception as exc:
        return 0, f"Failed to start FlightGear session: {exc}"


def create_voice_session(controller):
    subject_id = None
    voice_dir = None
    session_id = None

    if controller is not None:
        if getattr(controller, "subject", None) is not None:
            subject_id = controller.subject.get("id")
        if getattr(controller, "session", None):
            voice_dir = controller.session.voice_dir
            session_id = controller.session.session_id

    manager = VoiceSessionManager(
        subject_id=subject_id,
        session_id=session_id,
        recording_root=voice_dir,
    )
    manager.start_session()
    return manager


def finalize_voice_session(controller, manager):
    if manager is None:
        return None

    try:
        voice_data = manager.finalize_session()
        if voice_data and "summary" not in voice_data:
            voice_data["summary"] = manager._aggregate_summary()
    except VoiceSessionError as exc:
        voice_data = {
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
        }

    if controller is not None and hasattr(controller, "attach_voice_session_result"):
        controller.attach_voice_session_result(voice_data)

    return voice_data

