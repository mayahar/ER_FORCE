import copy
import json
from pathlib import Path


DATA_FILE = Path(__file__).with_name("database_data.json")


DEFAULT_SUBJECTS_DB = {
    1: {
        "id": 1,
        "name": "ישראל ישראלי",
        "sex": "male",
        "age": 28,
        "baseline": {
            "voice": {
                "dLPC": 0.42,
                "PARCOR": 0.55,
                "LPC": 0.61,
                "Pitch": 120.0,
                "MFCC": 0.50
            },
            "eye": {
                "fixation_duration": 0.22,
                "fixation_count": 120,
                "saccade_count": 150
            },
            "game": {
                "score": 85,
            }
        }
    },

    2: {
        "id": 2,
        "name": "שרה כהן",
        "sex": "female",
        "age": 25,
        "baseline": {
            "voice": {
                "dLPC": 0.40,
                "PARCOR": 0.53,
                "LPC": 0.60,
                "Pitch": 200.0,
                "MFCC": 0.55
            },
            "eye": {
                "fixation_duration": 0.20,
                "fixation_count": 125,
                "saccade_count": 160
            },
            "game": {
                "score": 80,
            }
        }
    }
}

DEFAULT_RESULTS_DB = []


def _load_database():
    if not DATA_FILE.exists():
        return copy.deepcopy(DEFAULT_SUBJECTS_DB), []

    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return copy.deepcopy(DEFAULT_SUBJECTS_DB), []

    raw_subjects = data.get("subjects", DEFAULT_SUBJECTS_DB)
    subjects = {
        int(subject_id): subject
        for subject_id, subject in raw_subjects.items()
    }

    results = data.get("results", [])
    return subjects, results


def save_database():
    data = {
        "subjects": SUBJECTS_DB,
        "results": RESULTS_DB,
    }

    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


SUBJECTS_DB, RESULTS_DB = _load_database()
