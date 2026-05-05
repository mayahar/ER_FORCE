import numpy as np

from score.fatigue_weights import (
    VOICE_WEIGHTS,
    EYE_WEIGHTS,
    MODALITY_WEIGHTS
)

from score.fatigue_variances import (
    VOICE_STD,
    EYE_STD,
    GAME_STD
)

VOICE_DIRECTION = {
    "dLPC": 1,
    "PARCOR": 1,
    "LPC": 1,
    "Pitch": 1,
    "MFCC": 1
}

EYE_DIRECTION = {
    "fixation_duration": 1,
    "fixation_count": 1,
    "saccade_count": 1
}

GAME_DIRECTION = {
    "score": -1
}


def safe_get(d, k):
    return d.get(k, None)


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


# =========================
# FEATURE SCORE
# =========================
def compute_feature_score(current, baseline, std=None, direction=1):

    if current is None or baseline is None:
        return None

    if std is not None:
        z = (current - baseline) / (std + 1e-8)
        return sigmoid(direction * z)

    delta = (current - baseline) / (abs(baseline) + 1e-8)
    return sigmoid(direction * delta)


# =========================
# VOICE + CONTRIBUTIONS
# =========================
def compute_voice_score(cur, base, info=None):

    contributions = {}

    total = 0
    wsum = 0

    sex = info.get("sex") if info else None

    for k, w in VOICE_WEIGHTS.items():

        c = safe_get(cur, k)
        b = safe_get(base, k)

        std = None
        direction = VOICE_DIRECTION.get(k, 1)

        if k == "Pitch" and sex:
            std = VOICE_STD["Pitch"].get(sex)
        elif k == "MFCC":
            std = VOICE_STD["MFCC"]

        s = compute_feature_score(c, b, std, direction)

        if s is None:
            continue

        contrib = w * s

        contributions[k] = {
            "value": float(contrib),
            "raw_score": float(s),
            "weight": w,
            "direction": direction
        }

        total += contrib
        wsum += w

    score = total / wsum if wsum else None

    return score, contributions


# =========================
# EYE + CONTRIBUTIONS
# =========================
def compute_eye_score(cur, base):

    contributions = {}

    total = 0
    wsum = 0

    for k, w in EYE_WEIGHTS.items():

        c = safe_get(cur, k)
        b = safe_get(base, k)

        std = EYE_STD.get(k)
        direction = EYE_DIRECTION.get(k, 1)

        s = compute_feature_score(c, b, std, direction)

        if s is None:
            continue

        contrib = w * s

        contributions[k] = {
            "value": float(contrib),
            "raw_score": float(s),
            "weight": w,
            "direction": direction
        }

        total += contrib
        wsum += w

    score = total / wsum if wsum else None

    return score, contributions


# =========================
# GAME + CONTRIBUTIONS
# =========================
def compute_game_score(cur, base):

    c = safe_get(cur, "score")
    b = safe_get(base, "score")

    if c is None or b is None:
        return None, {}

    std = GAME_STD.get("score")
    direction = GAME_DIRECTION["score"]

    s = compute_feature_score(c, b, std, direction)

    contrib = s  # single feature

    return s, {
        "score": {
            "value": float(contrib),
            "raw_score": float(s),
            "weight": 1.0,
            "direction": direction
        }
    }


# =========================
# FINAL SCORE + EXPLANATION
# =========================
def compute_fatigue_score(data):

    b = data["baseline"]
    c = data["current"]

    voice_score, voice_contrib = compute_voice_score(
        c["voice"],
        b["voice"],
        data.get("subject_info")
    )

    eye_score, eye_contrib = compute_eye_score(
        c["eye"],
        b["eye"]
    )

    game_score, game_contrib = compute_game_score(
        c["game"],
        b["game"]
    )

    scores = {
        "voice": voice_score,
        "eye": eye_score,
        "game": game_score
    }

    modality_contributions = {
        "voice": voice_contrib,
        "eye": eye_contrib,
        "game": game_contrib
    }

    num = 0
    den = 0

    for k, w in MODALITY_WEIGHTS.items():
        s = scores.get(k)

        if s is None:
            continue

        num += s * w
        den += w

    final = num / den if den else None

    return {
        "score": float(final * 100) if final is not None else None,
        "scores": scores,
        "feature_contributions": modality_contributions
    }