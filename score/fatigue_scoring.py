import numpy as np

from fatigue_weights import (
    VOICE_WEIGHTS,
    EYE_WEIGHTS,
    MODALITY_WEIGHTS
)

from fatigue_variances import (
    VOICE_STD,
    EYE_STD,
    GAME_STD
)

# =========================
# HELPERS
# =========================

def safe_get(d, key):
    return d[key] if key in d and d[key] is not None else None


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def compute_feature_score(current, baseline, std=None):
    if current is None or baseline is None:
        return None

    # CASE 1 — WITH POPULATION VARIANCE
    if std is not None and std != 0:
        z = (current - baseline) / std
        return sigmoid(abs(z))

    # CASE 2 — NO VARIANCE → RELATIVE CHANGE
    delta = (current - baseline) / (abs(baseline) + 1e-8)
    return sigmoid(abs(delta))


# =========================
# VOICE
# =========================

def compute_voice_score(current_voice, baseline_voice, subject_info=None):
    weighted_sum = 0.0
    weight_sum = 0.0

    sex = subject_info.get("sex") if subject_info else None

    for feature, weight in VOICE_WEIGHTS.items():
        cur = safe_get(current_voice, feature)
        base = safe_get(baseline_voice, feature)

        std = None

        if feature == "Pitch" and sex in ["male", "female"]:
            std = VOICE_STD["Pitch"][sex]

        elif feature == "MFCC":
            std = VOICE_STD["MFCC"]

        score = compute_feature_score(cur, base, std)

        if score is None:
            continue

        weighted_sum += score * weight
        weight_sum += weight

    return weighted_sum / weight_sum if weight_sum > 0 else None


# =========================
# EYE
# =========================

def compute_eye_score(current_eye, baseline_eye):
    weighted_sum = 0.0
    weight_sum = 0.0

    for feature, weight in EYE_WEIGHTS.items():
        cur = safe_get(current_eye, feature)
        base = safe_get(baseline_eye, feature)
        std = EYE_STD.get(feature)

        score = compute_feature_score(cur, base, std)

        if score is None:
            continue

        weighted_sum += score * weight
        weight_sum += weight

    return weighted_sum / weight_sum if weight_sum > 0 else None


# =========================
# GAME
# =========================

def compute_game_score(current_game, baseline_game):
    cur = safe_get(current_game, "score")
    base = safe_get(baseline_game, "score")
    std = GAME_STD.get("score")

    if cur is None or base is None:
        return None

    # performance drop = fatigue
    score = compute_feature_score(base, cur, std)

    return score


# =========================
# FINAL SCORE
# =========================

def compute_fatigue_score(data):
    baseline = data["baseline"]
    current = data["current"]

    subject_info = data.get("subject_info", {})

    voice_score = compute_voice_score(
        current.get("voice", {}),
        baseline.get("voice", {}),
        subject_info
    )

    eye_score = compute_eye_score(
        current.get("eye", {}),
        baseline.get("eye", {})
    )

    game_score = compute_game_score(
        current.get("game", {}),
        baseline.get("game", {})
    )

    scores = {
        "voice": voice_score,
        "eye": eye_score,
        "game": game_score
    }

    numerator = 0.0
    denominator = 0.0

    for modality, weight in MODALITY_WEIGHTS.items():
        score = scores.get(modality)

        if score is None:
            continue

        numerator += weight * score
        denominator += weight

    final_score = (numerator / denominator) if denominator > 0 else None

    return {
        "subject_id": data.get("subject_id"),
        "session_id": data.get("session_id"),

        "scores": scores,
        "modality_weights": MODALITY_WEIGHTS,

        "fatigue_score": float(final_score * 100) if final_score is not None else None
    }