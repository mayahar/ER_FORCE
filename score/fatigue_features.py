import json

with open("score/fatigue_features.json", "r", encoding="utf-8") as f:
    _data = json.load(f)

FEATURES = _data["FEATURES"]
MODALITY_WEIGHTS = _data["MODALITY_WEIGHTS"]