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
from core.session_manager import create_session



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

        import copy
        self.subject = copy.deepcopy(subject)

        self.subject["id"] = subject.get("id", subject_id)
        self.session = create_session(subject_id)

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
