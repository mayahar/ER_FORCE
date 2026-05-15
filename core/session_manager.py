from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
import json

REPO_ROOT = Path(__file__).resolve().parent.parent
SESSIONS_ROOT = REPO_ROOT / "sessions"


@dataclass
class SessionPaths:

    session_id: str

    root: Path

    voice_dir: Path

    eye_dir: Path

    game_dir: Path

    results_dir: Path


def create_session(subject_id: str):

    timestamp = datetime.now().strftime(
        "%Y-%m-%d_%H-%M-%S"
    )

    session_id = (
        f"{subject_id}_{timestamp}"
    )

    root = SESSIONS_ROOT / session_id
    root.mkdir(parents=True, exist_ok=True)

    voice_dir = root / "voice"
    eye_dir = root / "eye"
    game_dir = root / "game"
    results_dir = root / "results"

    voice_dir.mkdir(parents=True, exist_ok=True)
    eye_dir.mkdir(exist_ok=True)
    game_dir.mkdir(exist_ok=True)
    results_dir.mkdir(exist_ok=True)

    meta_data = {
        "subject_id": subject_id,
        "session_id": session_id,
        "created_at": timestamp
    }
    with open(root / "metadata.json", "w") as f:
        json.dump(meta_data, f, indent=4)

    print(f"Created session directory: {root}")

    return SessionPaths(
        session_id=session_id,
        root=root,
        voice_dir=voice_dir,
        eye_dir=eye_dir,
        game_dir=game_dir,
        results_dir=results_dir
    )
