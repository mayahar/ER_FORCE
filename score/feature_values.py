from numbers import Number


def is_unavailable_feature_value(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def coerce_feature_number(value):
    if is_unavailable_feature_value(value):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, Number):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None
