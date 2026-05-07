import time
import random

from core.subject_repository import get_subject
from score.fatigue_scoring import compute_fatigue_score


class MockController:

    def __init__(self):
        self.subject = None
        self.features = {}
        self.result = None

    # -------------------
    # DISPATCH (mock)
    # -------------------
    def dispatch(self, event, payload=None):
        pass

    # -------------------
    # LOAD SUBJECT
    # -------------------
    def load_subject(self, subject_id):

        subject = get_subject(subject_id)


        if subject is None:
            self.subject = None
            return False

        # 🔥 DEEP COPY (CRITICAL FIX)
        import copy
        self.subject = copy.deepcopy(subject)

        self.subject["id"] = subject_id

        self.features = {}
        self.result = None

        return True
    # -------------------
    # RUN SIMULATION
    # -------------------
    def run_multimodal_game(self):

        if self.subject is None:
            raise ValueError("No subject loaded")

        time.sleep(0.3)

        b = self.subject["baseline"]

        self.features = {
            "voice": {
                "dLPC": b["voice"]["dLPC"] * random.uniform(0.9, 1.1),
                "PARCOR": b["voice"]["PARCOR"] * random.uniform(0.9, 1.1),
                "LPC": b["voice"]["LPC"] * random.uniform(0.9, 1.1),
                "Pitch": b["voice"]["Pitch"] * random.uniform(0.95, 1.05),
                "MFCC": b["voice"]["MFCC"] * random.uniform(0.9, 1.1)
            },

            "eye": {
                "fixation_duration": b["eye"]["fixation_duration"] * random.uniform(1.0, 1.4),
                "fixation_count": b["eye"]["fixation_count"] * random.uniform(0.8, 1.2),
                "saccade_count": b["eye"]["saccade_count"] * random.uniform(0.9, 1.3)
            },

            "game": {
                "score": int(b["game"]["score"] * random.uniform(0.7, 0.95)),
            }
        }

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

        # 🔥 UPDATED RESULT SCHEMA
        self.result = {
            "subject_id": self.subject.get("id", "UNKNOWN"),
            "score": raw.get("score", 0),
            "scores": raw.get("scores", {}),
            "feature_contributions": raw.get("feature_contributions", {}),
            "features": self.features,
            "baseline": b
        }

        return self.result

    # -------------------
    # RESULT ACCESS
    # -------------------
    def get_result(self):
        return self.result or {
            "subject_id": self.subject.get("id") if self.subject else "UNKNOWN",
            "score": None,
            "scores": {},
            "features": self.features,
            "baseline": self.subject.get("baseline") if self.subject else {}
        }
    