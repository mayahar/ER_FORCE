import json

with open("fatigue_features_data.json", "r", encoding="utf-8") as f:
    _data = json.load(f)

FEATURES = _data["FEATURES"]
MODALITY_WEIGHTS = _data["MODALITY_WEIGHTS"]