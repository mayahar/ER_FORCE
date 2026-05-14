from score.eye_features import (
    EYE_FEATURE_KEYS,
    apply_controller_eye_features,
    has_eye_features,
    strip_absent_eye_from_result,
)
from score.feature_values import coerce_feature_number

VOICE_FEATURE_KEYS = ("dLPC", "PARCOR", "LPC", "Pitch", "MFCC")

__all__ = (
    "EYE_FEATURE_KEYS",
    "VOICE_FEATURE_KEYS",
    "apply_controller_eye_features",
    "compact_eye_features",
    "has_eye_features",
    "strip_absent_eye_from_result",
    "unused_voice_features",
    "voice_features_unused",
)


def unused_voice_features() -> dict:
    return {key: "none" for key in VOICE_FEATURE_KEYS}


def voice_features_unused(voice_features: dict | None) -> bool:
    if voice_features is None:
        return True
    return not any(
        coerce_feature_number(voice_features.get(key)) is not None
        for key in VOICE_FEATURE_KEYS
    )


def compact_eye_features(eye_features: dict) -> dict:
    compact = {
        key: eye_features[key]
        for key in EYE_FEATURE_KEYS
        if coerce_feature_number(eye_features.get(key)) is not None
    }
    analysis = eye_features.get("analysis")
    if analysis is not None:
        compact["analysis"] = analysis
    return compact
