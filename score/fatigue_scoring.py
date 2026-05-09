import numpy as np

from score.fatigue_features import (
    FEATURES,
    MODALITY_WEIGHTS
)

# =====================================================
# HELPERS
# =====================================================

def safe_get(d, k):
    return d.get(k, None)


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


# =====================================================
# FEATURE SCORE
# =====================================================

def compute_feature_score(
    current,
    baseline,
    feature_name,
    feature_cfg,
    sex=None
):

    if current is None or baseline is None:
        return None

    direction = feature_cfg["direction"]
    std = feature_cfg["std"]
    expected_change = feature_cfg["expected_change"]

    # -------------------------------------------------
    # RELATIVE CHANGE
    # -------------------------------------------------

    relative_change = (
        (current - baseline) /
        (abs(baseline) + 1e-8)
    )

    # -------------------------------------------------
    # NORMALIZE BY EXPECTED FATIGUE EFFECT
    # -------------------------------------------------

    normalized_effect = (
        relative_change /
        (expected_change + 1e-8)
    )

    # -------------------------------------------------
    # OPTIONAL POPULATION VARIANCE SCALING
    # -------------------------------------------------

    if std is not None:

        if isinstance(std, dict):
            std = std.get(sex)

        if std is not None:

            variance_scale = (
                abs(baseline) /
                (std + 1e-8)
            )

            normalized_effect *= variance_scale

    # -------------------------------------------------
    # APPLY DIRECTION
    # -------------------------------------------------

    signed_effect = direction * normalized_effect

    # -------------------------------------------------
    # SIGMOID
    # baseline -> 0.5
    # -------------------------------------------------

    raw = sigmoid(signed_effect)

    # -------------------------------------------------
    # RECENTER
    # baseline -> 0
    # fatigue -> positive
    # improvement -> negative
    # -------------------------------------------------

    centered = 2 * (raw - 0.5)

    return {
        "fatigue_score": centered,
        "raw_sigmoid": raw,
        "better_than_baseline": centered < 0,
        "relative_change": relative_change,
        "normalized_effect": normalized_effect
    }


# =====================================================
# MODALITY SCORE
# =====================================================

def compute_modality_score(
    modality_name,
    current_data,
    baseline_data,
    sex=None
):

    total = 0
    wsum = 0

    contributions = {}

    for feature_name, cfg in FEATURES.items():

        if cfg["modality"] != modality_name:
            continue

        current = safe_get(current_data, feature_name)
        baseline = safe_get(baseline_data, feature_name)

        result = compute_feature_score(
            current=current,
            baseline=baseline,
            feature_name=feature_name,
            feature_cfg=cfg,
            sex=sex
        )

        if result is None:
            continue

        fatigue_score = result["fatigue_score"]

        weight = cfg["weight"]

        weighted_contribution = (
            fatigue_score * weight
        )

        contributions[feature_name] = {

            # -----------------------------------
            # signed contribution
            # -----------------------------------

            "weighted_contribution": float(
                weighted_contribution
            ),

            # -----------------------------------
            # signed feature fatigue score
            # -----------------------------------

            "fatigue_score": float(
                fatigue_score
            ),

            # -----------------------------------
            # internal debug info
            # -----------------------------------

            "relative_change": float(
                result["relative_change"]
            ),

            "normalized_effect": float(
                result["normalized_effect"]
            ),

            "raw_sigmoid": float(
                result["raw_sigmoid"]
            ),

            "better_than_baseline": bool(
                result["better_than_baseline"]
            ),

            # -----------------------------------
            # metadata
            # -----------------------------------

            "weight": float(weight),

            "direction": int(
                cfg["direction"]
            ),

            "expected_change": float(
                cfg["expected_change"]
            ),

            "std": cfg["std"],

            "baseline": float(baseline),

            "current": float(current)
        }

        total += weighted_contribution
        wsum += weight

    modality_score = (
        total / wsum
        if wsum else None
    )

    return modality_score, contributions


# =====================================================
# FINAL FATIGUE SCORE
# =====================================================

def compute_fatigue_score(data):

    baseline = data["baseline"]
    current = data["current"]

    sex = (
        data
        .get("subject_info", {})
        .get("sex")
    )

    # =================================================
    # VOICE
    # =================================================

    voice_score, voice_contrib = (
        compute_modality_score(
            modality_name="voice",
            current_data=current["voice"],
            baseline_data=baseline["voice"],
            sex=sex
        )
    )

    # =================================================
    # EYE
    # =================================================

    eye_score, eye_contrib = (
        compute_modality_score(
            modality_name="eye",
            current_data=current["eye"],
            baseline_data=baseline["eye"]
        )
    )

    # =================================================
    # GAME
    # =================================================

    game_score, game_contrib = (
        compute_modality_score(
            modality_name="game",
            current_data=current["game"],
            baseline_data=baseline["game"]
        )
    )

    modality_scores = {
        "voice": voice_score,
        "eye": eye_score,
        "game": game_score
    }

    modality_contributions = {
        "voice": voice_contrib,
        "eye": eye_contrib,
        "game": game_contrib
    }

    # =================================================
    # FINAL AGGREGATION
    # =================================================

    numerator = 0
    denominator = 0

    modality_level_contributions = {}

    for modality, modality_weight in MODALITY_WEIGHTS.items():

        modality_score = modality_scores.get(modality)

        if modality_score is None:
            continue

        weighted_modality = (
            modality_score *
            modality_weight
        )

        modality_level_contributions[modality] = {
            "score": float(modality_score),
            "weight": float(modality_weight),
            "weighted_contribution": float(weighted_modality)
        }

        numerator += weighted_modality
        denominator += modality_weight

    final_score_raw = (
        numerator / denominator
        if denominator else None
    )

    # =================================================
    # DISPLAY SCORE
    # clip only at final UI level
    # =================================================

    if final_score_raw is not None:
        final_score_display = max(
            0.0,
            final_score_raw * 100
        )
    else:
        final_score_display = None

    # =================================================
    # GLOBAL BETTER-THAN-BASELINE FLAG
    # =================================================

    better_than_baseline = (
        final_score_raw is not None and
        final_score_raw < 0
    )

    # =================================================
    # RETURN
    # =================================================

    return {

        # ---------------------------------------------
        # UI score
        # clipped to >=0
        # ---------------------------------------------

        "score": (
            float(final_score_display)
            if final_score_display is not None
            else None
        ),

        # ---------------------------------------------
        # true internal raw score
        # can be negative
        # ---------------------------------------------

        "raw_score": (
            float(final_score_raw * 100)
            if final_score_raw is not None
            else None
        ),

        # ---------------------------------------------
        # modality-level scores
        # signed
        # ---------------------------------------------

        "scores": {
            k: (
                float(v * 100)
                if v is not None
                else None
            )
            for k, v in modality_scores.items()
        },

        # ---------------------------------------------
        # modality contribution to final score
        # ---------------------------------------------

        "modality_contributions":
            modality_level_contributions,

        # ---------------------------------------------
        # feature-level explainability
        # signed contributions
        # ---------------------------------------------

        "feature_contributions":
            modality_contributions,

        # ---------------------------------------------
        # global flag
        # ---------------------------------------------

        "better_than_baseline":
            better_than_baseline
    }