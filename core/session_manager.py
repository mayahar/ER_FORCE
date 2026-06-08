from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
import json

from core.research_repository import get_research_output_dir
from core.hardware_config import eye_tracker_configuration_snapshot

REPO_ROOT = Path(__file__).resolve().parent.parent
SESSIONS_ROOT = REPO_ROOT / "sessions"


def _tracker_initial_status(config: dict, tracker: str) -> dict:
    configured_key = "using_glasses" if tracker == "glasses" else "using_bar"
    enabled_key = (
        "glasses_calibration_enabled"
        if tracker == "glasses"
        else "bar_calibration_enabled"
    )
    configured = bool(config.get(configured_key))
    calibration_enabled = bool(config.get(enabled_key))
    if not configured:
        status = "not_configured"
    elif not calibration_enabled:
        status = "skipped_by_configuration"
    else:
        status = "pending"
    return {
        "configured": configured,
        "calibration_enabled": calibration_enabled,
        "attempted": False,
        "passed": None,
        "status": status,
    }


def initial_eye_tracker_calibration_status(config: dict | None = None) -> dict:
    config = config or eye_tracker_configuration_snapshot()
    return {
        "glasses": _tracker_initial_status(config, "glasses"),
        "bar": _tracker_initial_status(config, "bar"),
    }


def _runtime_tracker_status(runtime, tracker: str, config: dict) -> dict:
    status = _tracker_initial_status(config, tracker)
    configured = bool(status["configured"])
    if not configured:
        return status

    attempted = bool(getattr(runtime, "calibration_attempted", False)) if runtime else False
    passed = bool(getattr(runtime, "calibration_passed", False)) if runtime else None
    message = str(getattr(runtime, "calibration_message", "") or "") if runtime else ""
    calibration_enabled = bool(status["calibration_enabled"])

    status.update(
        {
            "attempted": attempted,
            "passed": passed if attempted else (True if not calibration_enabled else None),
            "message": message,
        }
    )
    if not calibration_enabled:
        status["status"] = "skipped_by_configuration"
    elif attempted and passed:
        status["status"] = "passed"
    elif attempted:
        status["status"] = "failed"
    else:
        status["status"] = "pending"

    preview_path = getattr(runtime, "calibration_preview_path", None) if runtime else None
    if preview_path:
        status["preview_path"] = str(preview_path)
    summary = getattr(runtime, "calibration_summary", None) if runtime else None
    if summary:
        status["result"] = summary
    return status


def eye_tracker_calibration_status_from_runtime(runtime, config: dict | None = None) -> dict:
    config = config or eye_tracker_configuration_snapshot()
    glasses_runtime = getattr(runtime, "glasses", None)
    bar_runtime = getattr(runtime, "bar", None)
    mode = config.get("eye_tracker_mode")
    if glasses_runtime is None and bar_runtime is None:
        if mode == "glasses":
            glasses_runtime = runtime
        elif mode == "bar":
            bar_runtime = runtime

    return {
        "glasses": _runtime_tracker_status(glasses_runtime, "glasses", config),
        "bar": _runtime_tracker_status(bar_runtime, "bar", config),
    }


def update_session_metadata(session, updates: dict) -> None:
    root = getattr(session, "root", None)
    if root is None:
        return
    metadata_path = Path(root) / "metadata.json"
    try:
        metadata = {}
        if metadata_path.is_file():
            with metadata_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                metadata = data
        metadata.update(updates)
        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4, ensure_ascii=False)
            f.write("\n")
    except Exception:
        pass


@dataclass
class SessionPaths:

    session_id: str

    root: Path

    voice_dir: Path

    eye_dir: Path

    glasses_eye_dir: Path

    bar_eye_dir: Path

    game_dir: Path

    results_dir: Path


def create_session(subject_id: str, research_context=None):

    timestamp = datetime.now().strftime(
        "%Y-%m-%d_%H-%M-%S"
    )

    session_id = (
        f"{subject_id}_{timestamp}"
    )

    if research_context:
        root = get_research_output_dir(research_context, subject_id) / "sessions" / session_id
    else:
        root = SESSIONS_ROOT / session_id
    root.mkdir(parents=True, exist_ok=True)

    voice_dir = root / "voice"
    eye_dir = root / "eye"
    game_dir = root / "game"
    results_dir = root / "results"

    voice_dir.mkdir(parents=True, exist_ok=True)
    eye_dir.mkdir(exist_ok=True)
    glasses_eye_dir = eye_dir / "glasses"
    bar_eye_dir = eye_dir / "bar"
    glasses_eye_dir.mkdir(exist_ok=True)
    bar_eye_dir.mkdir(exist_ok=True)
    game_dir.mkdir(exist_ok=True)
    results_dir.mkdir(exist_ok=True)

    eye_tracker_config = eye_tracker_configuration_snapshot()
    meta_data = {
        "subject_id": subject_id,
        "session_id": session_id,
        "created_at": timestamp,
        "eye_tracker_configuration": eye_tracker_config,
        "eye_tracker_calibration_status": initial_eye_tracker_calibration_status(
            eye_tracker_config
        ),
    }
    with open(root / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta_data, f, indent=4, ensure_ascii=False)

    print(f"Created session directory: {root}")

    return SessionPaths(
        session_id=session_id,
        root=root,
        voice_dir=voice_dir,
        eye_dir=eye_dir,
        glasses_eye_dir=glasses_eye_dir,
        bar_eye_dir=bar_eye_dir,
        game_dir=game_dir,
        results_dir=results_dir
    )
