import unicodedata

from core.database import SUBJECTS_DB, save_database


EMPTY_BASELINE = {
    "voice": {},
    "eye": {},
    "game": {},
}


def _parse_int(value):
    """
    Parses numeric UI input while ignoring invisible RTL formatting marks.
    """
    if isinstance(value, bool):
        raise ValueError("Boolean values are not valid numeric identifiers")

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise ValueError("Expected an integer value")

    text = str(value).strip()
    normalized_chars = []

    for char in text:
        if char.isspace() or unicodedata.category(char) == "Cf":
            continue

        try:
            normalized_chars.append(str(unicodedata.decimal(char)))
        except (TypeError, ValueError):
            normalized_chars.append(char)

    normalized = "".join(normalized_chars)

    if not normalized:
        raise ValueError("Expected a numeric value")

    return int(normalized)


def get_subject(subject_id):
    """
    Returns subject dict or None
    """
    try:
        sid = _parse_int(subject_id)
        return SUBJECTS_DB.get(sid)
    except (ValueError, TypeError):
        return None


def subject_exists(subject_id):
    return get_subject(subject_id) is not None


def get_all_subjects():
    return list(SUBJECTS_DB.values())


def get_all_subject_ids():
    return sorted(SUBJECTS_DB.keys())


def create_subject(subject_id, name=None, sex="unknown", age=0):
    """
    Creates a new subject without measured baseline data.
    """
    sid = _parse_int(subject_id)

    if sid in SUBJECTS_DB:
        return SUBJECTS_DB[sid]

    clean_name = str(name).strip() if name is not None else ""
    clean_sex = str(sex).strip().lower() if sex is not None else "unknown"
    clean_age = _parse_int(age)

    SUBJECTS_DB[sid] = {
        "id": sid,
        "name": clean_name or f"Subject {sid}",
        "sex": clean_sex or "unknown",
        "age": clean_age,
        "baseline": {k: v.copy() for k, v in EMPTY_BASELINE.items()},
    }

    save_database()
    return SUBJECTS_DB[sid]


def create_or_update_subject_profile(subject_id, name=None, sex="unknown", age=0):
    """
    Creates a subject or updates only their profile fields, preserving baseline data.
    """
    sid = _parse_int(subject_id)

    if sid not in SUBJECTS_DB:
        return create_subject(sid, name=name, sex=sex, age=age)

    clean_name = str(name).strip() if name is not None else ""
    clean_sex = str(sex).strip().lower() if sex is not None else "unknown"
    clean_age = _parse_int(age)

    SUBJECTS_DB[sid]["id"] = sid
    SUBJECTS_DB[sid]["name"] = clean_name or SUBJECTS_DB[sid].get("name") or f"Subject {sid}"
    SUBJECTS_DB[sid]["sex"] = clean_sex or SUBJECTS_DB[sid].get("sex") or "unknown"
    SUBJECTS_DB[sid]["age"] = clean_age
    SUBJECTS_DB[sid].setdefault(
        "baseline",
        {k: v.copy() for k, v in EMPTY_BASELINE.items()},
    )

    save_database()
    return SUBJECTS_DB[sid]


def update_subject_baseline(subject_id, baseline):
    """
    Stores measured baseline features for an existing subject.
    """
    sid = _parse_int(subject_id)

    if sid not in SUBJECTS_DB:
        raise KeyError(f"Subject {sid} does not exist")

    SUBJECTS_DB[sid]["baseline"] = baseline
    save_database()
    return SUBJECTS_DB[sid]


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
