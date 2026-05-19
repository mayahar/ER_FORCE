from score.feature_values import coerce_feature_number

EYE_FEATURE_KEYS = ("fixation_duration", "fixation_count", "saccade_count")


def has_eye_features(eye_features: dict | None) -> bool:
    if not isinstance(eye_features, dict) or not eye_features:
        return False
    return any(
        coerce_feature_number(eye_features.get(key)) is not None
        for key in EYE_FEATURE_KEYS
    )


def apply_controller_eye_features(controller, eye_features) -> None:
    if not hasattr(controller, "set_eye_features"):
        return
    if has_eye_features(eye_features):
        controller.set_eye_features(eye_features)
    else:
        controller.set_eye_features(None)


def apply_eye_features_fallback(controller) -> None:
    apply_controller_eye_features(controller, None)


def strip_absent_eye_from_result(result: dict) -> dict:
    features = result.get("features") or {}
    if has_eye_features(features.get("eye")):
        return result

    contributions = result.get("feature_contributions") or {}
    if "eye" in contributions:
        contributions = dict(contributions)
        contributions.pop("eye", None)
        result["feature_contributions"] = contributions

    scores = result.get("scores") or {}
    if "eye" in scores:
        scores = dict(scores)
        scores.pop("eye", None)
        result["scores"] = scores

    if "eye" in features:
        features = dict(features)
        features.pop("eye", None)
        result["features"] = features

    return result
