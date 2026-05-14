import time
import random

from core.subject_repository import get_subject
from core.fg_run_score import find_latest_flightgear_score
from core.modality_features import (
    compact_eye_features,
    has_eye_features,
    strip_absent_eye_from_result,
    unused_voice_features,
    voice_features_unused,
)
from score.feature_values import coerce_feature_number
from score.fatigue_scoring import compute_fatigue_score


def _baseline_scalar(value, fallback: float) -> float:
    number = coerce_feature_number(value)
    return number if number is not None else fallback


def _mock_voice_features(baseline: dict) -> dict:
    voice = baseline.get("voice") or {}
    return {
        "dLPC": _baseline_scalar(voice.get("dLPC"), 0.41) * random.uniform(0.9, 1.1),
        "PARCOR": _baseline_scalar(voice.get("PARCOR"), 0.54) * random.uniform(0.9, 1.1),
        "LPC": _baseline_scalar(voice.get("LPC"), 0.60) * random.uniform(0.9, 1.1),
        "Pitch": _baseline_scalar(voice.get("Pitch"), 150.0) * random.uniform(0.95, 1.05),
        "MFCC": _baseline_scalar(voice.get("MFCC"), 0.52) * random.uniform(0.9, 1.1),
    }


class Controller:

    def __init__(self):
        self.subject = None
        self.features = {}
        self.questionnaire = {}
        self.result = None
        self.recorded_voice_features = None
        self.recorded_eye_features = None
        self.recorded_game_score = None

    # -------------------
    # DISPATCH (mock)
    # -------------------
    def dispatch(self, event, payload=None):
        if event == "QUESTIONNAIRE_DONE":
            self.questionnaire = payload or {}

    # -------------------
    # LOAD SUBJECT
    # -------------------
    def load_subject(self, subject_id):

        subject = get_subject(subject_id)

        if subject is None:
            self.subject = None
            return False

        import copy
        self.subject = copy.deepcopy(subject)

        self.subject["id"] = subject.get("id", subject_id)

        self.features = {}
        self.questionnaire = {}
        self.result = None
        self.recorded_voice_features = None
        self.recorded_eye_features = None
        self.recorded_game_score = None

        return True

    # -------------------
    # RUN SIMULATION
    # -------------------
    def set_voice_features(self, voice_features: dict | None):
        self.recorded_voice_features = voice_features

    def set_eye_features(self, eye_features: dict | None):
        self.recorded_eye_features = eye_features

    def set_game_score(self, score: int | None):
        self.recorded_game_score = score

    def get_voice_dlpc(self):
        return self._resolve_voice_features().get("dLPC")

    def get_voice_parcor(self):
        return self._resolve_voice_features().get("PARCOR")

    def get_voice_lpc(self):
        return self._resolve_voice_features().get("LPC")

    def get_voice_pitch(self):
        return self._resolve_voice_features().get("Pitch")

    def get_voice_mfcc(self):
        return self._resolve_voice_features().get("MFCC")

    def _resolve_voice_features(self, baseline: dict | None = None) -> dict:
        if self.features.get("voice"):
            return self.features["voice"]
        if baseline is None:
            baseline = (self.subject or {}).get("baseline") or {}
        if self.recorded_voice_features is not None:
            if voice_features_unused(self.recorded_voice_features):
                return unused_voice_features()
            return self.recorded_voice_features
        if baseline:
            return _mock_voice_features(baseline)
        return unused_voice_features()

    def run_multimodal_game(self):

        if self.subject is None:
            raise ValueError("No subject loaded")

        time.sleep(0.3)

        b = self.subject.get("baseline") or {}

        if not b.get("voice") or not b.get("eye") or not b.get("game"):
            b = {
                "voice": {
                    "dLPC": 0.41,
                    "PARCOR": 0.54,
                    "LPC": 0.60,
                    "Pitch": 150.0,
                    "MFCC": 0.52,
                },
                "eye": {
                    "fixation_duration": 0.21,
                    "fixation_count": 122,
                    "saccade_count": 155,
                },
                "game": {"score": 82},
            }

        fg_score = self.recorded_game_score
        if fg_score is None:
            fg_score = self._try_get_latest_flightgear_score()

        voice_features = self.recorded_voice_features
        if voice_features is None:
            voice_features = _mock_voice_features(b)
        elif voice_features_unused(voice_features):
            voice_features = unused_voice_features()

        self.features = {
            "voice": voice_features,
            "game": {
                "score": (
                    int(fg_score)
                    if fg_score is not None
                    else int(
                        _baseline_scalar(b["game"].get("score"), 82)
                        * random.uniform(0.7, 0.95)
                    )
                ),
            },
            "questionnaire": self.questionnaire.copy(),
        }

        if has_eye_features(self.recorded_eye_features):
            self.features["eye"] = compact_eye_features(self.recorded_eye_features)

    def _try_get_latest_flightgear_score(self) -> int | None:
        return find_latest_flightgear_score()

    # -------------------
    # SCORING
    # -------------------
    def compute_fatigue(self):

        if self.subject is None:
            raise ValueError("No subject loaded")

        if not self.features:
            raise ValueError("No features computed (run game first)")

        b = self.subject["baseline"]

        data = {
            "baseline": b,
            "current": self.features,
            "subject_info": {
                "sex": self.subject.get("sex"),
                "age": self.subject.get("age"),
            },
        }

        raw = compute_fatigue_score(data)

        self.result = strip_absent_eye_from_result({
            "subject_id": self.subject.get("id", "UNKNOWN"),
            "subject_info": {
                "name": self.subject.get("name"),
                "sex": self.subject.get("sex"),
                "age": self.subject.get("age"),
            },
            "score": raw.get("score", 0),
            "scores": raw.get("scores", {}),
            "feature_contributions": raw.get("feature_contributions", {}),
            "features": self.features,
            "baseline": b,
        })

        return self.result

    # -------------------
    # RESULT ACCESS
    # -------------------
    def get_result(self):
        return self.result or {
            "subject_id": self.subject.get("id") if self.subject else "UNKNOWN",
            "subject_info": {
                "name": self.subject.get("name") if self.subject else None,
                "sex": self.subject.get("sex") if self.subject else None,
                "age": self.subject.get("age") if self.subject else None,
            },
            "score": None,
            "scores": {},
            "features": self.features,
            "baseline": self.subject.get("baseline") if self.subject else {},
        }
