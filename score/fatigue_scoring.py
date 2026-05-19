import numpy as np

from score.eye_features import has_eye_features
from score.feature_values import coerce_feature_number
from score.fatigue_features import (
    FEATURES,
    MODALITY_WEIGHTS
)

# =====================================================
# HELPERS
# =====================================================

def safe_get(d, k):
    return d.get(k, None)


def _export_feature_value(value):
    number = coerce_feature_number(value)
    if number is None:
        return None
    return float(number)


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

    current_value = coerce_feature_number(current)
    baseline_value = coerce_feature_number(baseline)

    if current_value is None or baseline_value is None:
        return None

    current = current_value
    baseline = baseline_value

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


def compute_absolute_feature_score(current, feature_cfg):

    current_value = coerce_feature_number(current)
    if current_value is None:
        return None

    current = current_value

    minimum = feature_cfg.get("min")
    maximum = feature_cfg.get("max")
    if minimum is None or maximum is None:
        valid_range = feature_cfg.get("MEASUREMENT_VALID_RANGES")
        if isinstance(valid_range, tuple) and len(valid_range) == 2:
            minimum, maximum = valid_range

    if minimum is None or maximum is None or maximum == minimum:
        return None

    normalized = (current - minimum) / (maximum - minimum)
    normalized = min(1.0, max(0.0, normalized))

    fatigue_score = feature_cfg["direction"] * ((2 * normalized) - 1)

    # Derive a raw sigmoid-like value so absolute-scored features expose
    # a compatible "raw_sigmoid" for exports and debugging. This mirrors
    # the transform used for relative features where:
    #   centered = 2*(raw - 0.5)  =>  raw = (centered / 2) + 0.5
    raw_sigmoid = (fatigue_score / 2.0) + 0.5

    return {
        "fatigue_score": fatigue_score,
        "raw_sigmoid": float(raw_sigmoid),
        "better_than_baseline": fatigue_score < 0,
        "relative_change": None,
        # keep the previous behaviour where normalized_effect carried the
        # signed score for downstream code; this keeps semantics stable.
        "normalized_effect": float(fatigue_score)
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
        current_num = coerce_feature_number(current)
        baseline_num = coerce_feature_number(baseline)

        if cfg.get("scoring") == "absolute":
            if current_num is None:
                continue
            result = compute_absolute_feature_score(
                current=current_num,
                feature_cfg=cfg
            )
        else:
            if current_num is None or baseline_num is None:
                continue
            result = compute_feature_score(
                current=current_num,
                baseline=baseline_num,
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

            "relative_change": (
                float(result["relative_change"])
                if result["relative_change"] is not None
                else None
            ),

            "normalized_effect": (
                float(result["normalized_effect"])
                if result["normalized_effect"] is not None
                else None
            ),

            "raw_sigmoid": (
                float(result["raw_sigmoid"])
                if result["raw_sigmoid"] is not None
                else None
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

            "expected_change": (
                float(cfg["expected_change"])
                if cfg["expected_change"] is not None
                else None
            ),

            "std": cfg["std"],

            "baseline": _export_feature_value(baseline),

            "current": _export_feature_value(current)
        }

        total += weighted_contribution
        wsum += weight

    if wsum:
        modality_score = total / wsum
    else:
        scored = [
            item["fatigue_score"]
            for item in contributions.values()
            if item.get("fatigue_score") is not None
        ]
        if scored:
            modality_score = sum(scored) / len(scored)
        else:
            modality_score = None

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
            current_data=current.get("voice", {}),
            baseline_data=baseline.get("voice", {}),
            sex=sex
        )
    )

    # =================================================
    # EYE
    # =================================================

    if has_eye_features(current.get("eye")):
        eye_score, eye_contrib = (
            compute_modality_score(
                modality_name="eye",
                current_data=current.get("eye", {}),
                baseline_data=baseline.get("eye", {})
            )
        )
    else:
        eye_score, eye_contrib = None, {}

    # =================================================
    # GAME
    # =================================================

    game_score, game_contrib = (
        compute_modality_score(
            modality_name="game",
            current_data=current.get("game", {}),
            baseline_data=baseline.get("game", {})
        )
    )

    # =================================================
    # SUBJECTIVE QUESTIONNAIRE
    # =================================================

    subjective_score, subjective_contrib = (
        compute_modality_score(
            modality_name="subjective",
            current_data=current.get("questionnaire", {}),
            baseline_data=baseline.get("questionnaire", {})
        )
    )

    modality_scores = {
        "voice": voice_score,
        "game": game_score,
        "subjective": subjective_score,
    }
    if eye_score is not None:
        modality_scores["eye"] = eye_score

    modality_contributions = {
        "voice": voice_contrib,
        "game": game_contrib,
        "subjective": subjective_contrib,
    }
    if eye_contrib:
        modality_contributions["eye"] = eye_contrib

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
