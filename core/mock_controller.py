import time
import random
import os
import re
from pathlib import Path

from core.subject_repository import get_subject
from score.fatigue_scoring import compute_fatigue_score
from core.session_manager import create_session



class Controller:

    def __init__(self):
        self.session = None
        self.subject = None
        self.features = {}
        self.questionnaire = {}
        self.result = None
        self.voice_session_data = None

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

        # 🔥 DEEP COPY (CRITICAL FIX)
        import copy
        self.subject = copy.deepcopy(subject)

        self.subject["id"] = subject.get("id", subject_id)
        self.session = create_session(subject_id)

        self.features = {}
        self.questionnaire = {}
        self.result = None

        return True
    # -------------------
    # RUN SIMULATION
    # -------------------
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

        fg_score = self._try_get_latest_flightgear_score()

        voice_summary = None
        voice_events = []

        if self.voice_session_data:
            voice_summary = self.voice_session_data.get("summary", {})
            voice_events = self.voice_session_data.get("events", [])

        self.features = {
            "voice": {
                "dLPC": voice_summary.get("dLPC"),
                "PARCOR": voice_summary.get("PARCOR"),
                "LPC": voice_summary.get("LPC"),
                "Pitch": voice_summary.get("Pitch"),
                "MFCC": voice_summary.get("MFCC"),
                "events": voice_events,
            },

            "eye": {
                "fixation_duration": b["eye"]["fixation_duration"] * random.uniform(1.0, 1.4),
                "fixation_count": b["eye"]["fixation_count"] * random.uniform(0.8, 1.2),
                "saccade_count": b["eye"]["saccade_count"] * random.uniform(0.9, 1.3)
            },

            "game": {
                # Prefer the real FlightGear score (from logging_fg_start_ver5.py final_score.txt).
                # Fallback to the prior mock behavior if we can't find a recent run.
                "score": int(fg_score) if fg_score is not None else int(b["game"]["score"] * random.uniform(0.7, 0.95)),
            },

            "questionnaire": self.questionnaire.copy()
        }

    def attach_voice_session_result(self, session_data):
        self.voice_session_data = session_data or {}

    def _try_get_latest_flightgear_score(self) -> int | None:
        
        # 1. בדיקה ראשונה: האם קיים ציון בסשן הנוכחי (המיקום החדש)
        if self.session and self.session.game_dir:
            report = self.session.game_dir / "final_score.txt"
            if report.exists():
                try:
                    text = report.read_text(encoding="utf-8", errors="ignore")
                    m = re.search(r"Score:\s*(\d+)\s*/\s*100", text)
                    if m:
                        score = int(m.group(1))
                        return max(0, min(100, score))
                except OSError:
                    pass

        # 2. לוגיקה ישנה/גיבוי: חיפוש בתיקיית הריצות הכללית
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
            sessions = [p for p in sessions if p.stat().st_mtime >= (min_ts - 1.0)]
            if not sessions:
                return None

        sessions.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        for session in sessions[:10]:
            report = session / "final_score.txt"
            if not report.exists():
                continue
            try:
                text = report.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            m = re.search(r"Score:\s*(\d+)\s*/\s*100", text)
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

        # 🔥 UPDATED RESULT SCHEMA
        self.result = {
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
            "baseline": b
        }

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
            "baseline": self.subject.get("baseline") if self.subject else {}
        }
    
