from core.database import SUBJECTS_DB, RESULTS_DB

def get_subject(subject_id):
    """
    Returns subject dict or None
    """
    try:
        sid = int(subject_id)
        return SUBJECTS_DB.get(sid)
    except (ValueError, TypeError):
        return None


def subject_exists(subject_id):
    return get_subject(subject_id) is not None


def get_all_subjects():
    return list(SUBJECTS_DB.values())


def get_all_subject_ids():
    return sorted(SUBJECTS_DB.keys())


def create_subject(subject_id):
    """
    Creates a new subject with default baseline.
    """
    sid = int(subject_id)

    if sid in SUBJECTS_DB:
        return SUBJECTS_DB[sid]

    SUBJECTS_DB[sid] = {
        "id": sid,
        "name": f"נושא {sid}",
        "sex": "unknown",
        "age": 0,
        "baseline": {
            "voice": {
                "dLPC": 0.41,
                "PARCOR": 0.54,
                "LPC": 0.60,
                "Pitch": 150.0,
                "MFCC": 0.52,
            },
            "eye": {
                "fixation_duration": 0.21,
                "fixation_count": 122,
                "saccade_count": 155,
            },
            "game": {"score": 82},
        },
    }

    return SUBJECTS_DB[sid]


def save_result_object(result):
    """
    Persist a full result object with subject id.
    """
    if not result:
        return

    RESULTS_DB.append(result)


# =========================
# VALIDATION (IMPORTANT)
# =========================

REQUIRED_KEYS = {
    "voice": {"dLPC", "PARCOR", "LPC", "Pitch", "MFCC"},
    "eye": {"fixation_duration", "fixation_count", "saccade_count"},
    "game": {"score"}
}


def validate_subject(subject):
    """
    Ensures subject matches scoring schema
    """
    if not subject:
        return False

    try:
        baseline = subject["baseline"]

        for modality, keys in REQUIRED_KEYS.items():
            if modality not in baseline:
                return False

            for k in keys:
                if k not in baseline[modality]:
                    return False

        return True

    except Exception:
        return False


def get_valid_subject(subject_id):
    """
    Safe getter with validation
    """
    subject = get_subject(subject_id)

    if not validate_subject(subject):
        return None

    return subject
