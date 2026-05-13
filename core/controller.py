import time
import os
import re
from pathlib import Path

from core.subject_repository import get_subject
from score.fatigue_scoring import compute_fatigue_score


class Controller:

    def __init__(self):
        self.subject = None
        self.features = {}
        self.questionnaire = {}
        self.result = None
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
        self.recorded_eye_features = None
        self.recorded_game_score = None

        return True

    # -------------------
    # RUN MULTIMODAL GAME
    # -------------------
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

        eye_features = self.recorded_eye_features
        if eye_features is None:
            eye_features = {
                "fixation_duration": self.get_fixation_duration(),
                "fixation_count": self.get_fixation_count(),
                "saccade_count": self.get_saccade_count()
            }

        self.features = {
            "voice": {
                "dLPC": self.get_voice_dlpc(),
                "PARCOR": self.get_voice_parcor(),
                "LPC": self.get_voice_lpc(),
                "Pitch": self.get_voice_pitch(),
                "MFCC": self.get_voice_mfcc()
            },

            "eye": eye_features,

            "game": {
                "score": fg_score
            },

            "questionnaire": self.questionnaire.copy()
        }

    # -------------------
    # REAL DATA FUNCTIONS
    # -------------------

    # ---- Voice ----
    def get_voice_dlpc(self):
        return None

    def get_voice_parcor(self):
        return None

    def get_voice_lpc(self):
        return None

    def get_voice_pitch(self):
        return None

    def get_voice_mfcc(self):
        return None

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

        runs_root = os.environ.get(
            "SIVAKS_FG_RUNS_ROOT",
            r"C:\Users\srule\OneDrive\Desktop\yan\FlightGear_2020_3\sivaks_logging_version\runs",
        )

        root = Path(runs_root)

        if not root.exists() or not root.is_dir():
            return None

        sessions = [p for p in root.glob("session_*") if p.is_dir()]

        if not sessions:
            return None

        min_ts = None

        try:
            raw_min_ts = os.environ.get("SIVAKS_FG_MIN_START_TS")

            if raw_min_ts:
                min_ts = float(raw_min_ts)

        except Exception:
            min_ts = None

        if min_ts is not None:
            sessions = [
                p for p in sessions
                if p.stat().st_mtime >= (min_ts - 1.0)
            ]

            if not sessions:
                return None

        sessions.sort(
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        for session in sessions[:10]:

            report = session / "final_score.txt"

            if not report.exists():
                continue

            try:
                text = report.read_text(
                    encoding="utf-8",
                    errors="ignore"
                )

            except OSError:
                continue

            m = re.search(
                r"Score:\s*(\d+)\s*/\s*100",
                text
            )

            if m:
                score = int(m.group(1))
                return max(0, min(100, score))

        return None

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

        self.result = {
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
        }

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
