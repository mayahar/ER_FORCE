import time
import os

from core.subject_repository import get_subject
from core.fg_run_score import find_latest_flightgear_score
from core.modality_features import (
    compact_eye_features,
    has_eye_features,
    strip_absent_eye_from_result,
    unused_voice_features,
    voice_features_unused,
)
from score.fatigue_scoring import compute_fatigue_score


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
    # DISPATCH
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

        # DEEP COPY
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
    # RUN MULTIMODAL GAME
    # -------------------
    def set_voice_features(self, voice_features: dict | None):
        self.recorded_voice_features = voice_features

    def set_eye_features(self, eye_features: dict | None):
        self.recorded_eye_features = eye_features

    def set_game_score(self, score: int | None):
        self.recorded_game_score = score

    def run_multimodal_game(self):

        if self.subject is None:
            raise ValueError("No subject loaded")

        time.sleep(0.3)

        fg_score = self.recorded_game_score
        if fg_score is None:
            fg_score = self._try_get_latest_flightgear_score()

        voice_features = self.recorded_voice_features
        if voice_features is None or voice_features_unused(voice_features):
            voice_features = unused_voice_features()

        self.features = {
            "voice": voice_features,
            "game": {
                "score": fg_score
            },
            "questionnaire": self.questionnaire.copy()
        }

        if has_eye_features(self.recorded_eye_features):
            self.features["eye"] = compact_eye_features(self.recorded_eye_features)

    # -------------------
    # REAL DATA FUNCTIONS
    # -------------------

    # ---- Voice ----
    def get_voice_dlpc(self):
        return self._voice_feature_value("dLPC")

    def get_voice_parcor(self):
        return self._voice_feature_value("PARCOR")

    def get_voice_lpc(self):
        return self._voice_feature_value("LPC")

    def get_voice_pitch(self):
        return self._voice_feature_value("Pitch")

    def get_voice_mfcc(self):
        return self._voice_feature_value("MFCC")

    def _voice_feature_value(self, key: str):
        voice_features = self.features.get("voice") or self.recorded_voice_features
        if isinstance(voice_features, dict) and key in voice_features:
            return voice_features.get(key)
        return "none"

    # ---- Eye Tracking ----
    def get_fixation_duration(self):
        return None

    def get_fixation_count(self):
        return None

    def get_saccade_count(self):
        return None

    # -------------------
    # FLIGHTGEAR SCORE
    # -------------------
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
                "age": self.subject.get("age")
            }
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
            "feature_contributions": raw.get(
                "feature_contributions",
                {}
            ),
            "features": self.features,
            "baseline": b
        })

        return self.result

    # -------------------
    # RESULT ACCESS
    # -------------------
    def get_result(self):

        return self.result or {
            "subject_id": (
                self.subject.get("id")
                if self.subject
                else "UNKNOWN"
            ),
            "subject_info": {
                "name": (
                    self.subject.get("name")
                    if self.subject
                    else None
                ),
                "sex": (
                    self.subject.get("sex")
                    if self.subject
                    else None
                ),
                "age": (
                    self.subject.get("age")
                    if self.subject
                    else None
                ),
            },
            "score": None,
            "scores": {},
            "features": self.features,
            "baseline": (
                self.subject.get("baseline")
                if self.subject
                else {}
            )
        }
