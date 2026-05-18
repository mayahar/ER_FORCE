import math
import time
import os

from core.subject_repository import get_subject
from core.session_manager import create_session
from score.fatigue_features import FEATURES
from core.fg_run_score import find_latest_flightgear_score
from core.modality_features import (
    compact_eye_features,
    has_eye_features,
    strip_absent_eye_from_result,
    unused_voice_features,
    voice_features_unused,
)
from score.fatigue_scoring import compute_fatigue_score


MODALITY_WARNING_LABELS = {
    "voice": "קול",
    "eye": "תנועות עיניים",
    "game": "משחק",
}


class Controller:

    def __init__(self):
        self.session = None
        self.subject = None
        self.features = {}
        self.questionnaire = {}
        self.result = None
        self.voice_session_data = None
        self.measurement_warnings = []
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
        self.session = create_session(subject_id)

        self.features = {}
        self.questionnaire = {}
        self.result = None
        self.voice_session_data = None
        self.measurement_warnings = []
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

        self.measurement_warnings = []
        voice_features, voice_events = self._collect_voice_features()
        eye_features = self._collect_eye_features()
        game_features = self._collect_game_features()

        voice_features = self.recorded_voice_features
        if voice_features is None or voice_features_unused(voice_features):
            voice_features = unused_voice_features()

        self.features = {
            "voice": {**voice_features, "events": voice_events},
            "eye": eye_features,
            "game": game_features,
            "questionnaire": self.questionnaire.copy()
        }

        if has_eye_features(self.recorded_eye_features):
            self.features["eye"] = compact_eye_features(self.recorded_eye_features)

    def attach_voice_session_result(self, session_data):
        self.voice_session_data = session_data or {}

    def _warn_measurement(self, modality, detail):
        label = MODALITY_WARNING_LABELS.get(modality, modality)
        warning = {
            "modality": modality,
            "label": label,
            "detail": str(detail),
        }
        self.measurement_warnings.append(warning)
        print(f"[ER Force warning] {label}: {detail}")

    def _none_features(self, modality):
        return {
            feature: None
            for feature in self._measurement_features(modality)
        }

    def _measurement_features(self, modality):
        return {
            feature: cfg
            for feature, cfg in FEATURES.items()
            if cfg.get("modality") == modality
            and cfg.get("MEASUREMENT_VALID_RANGES") is not None
        }

    def _coerce_valid_number(self, modality, feature, value):
        if value is None or isinstance(value, bool):
            return self._voice_feature_value("dLPC")

        try:
            number = float(value)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(number):
            return None

        valid_range = FEATURES[feature].get("MEASUREMENT_VALID_RANGES")
        if valid_range is None:
            return number

        minimum, maximum = valid_range
        if number < minimum or number > maximum:
            return None

        return number

    def _validate_modality_features(self, modality, values):
        validated = {}
        invalid = []

        for feature in self._measurement_features(modality):
            value = self._coerce_valid_number(
                modality,
                feature,
                values.get(feature)
            )
            if value is None:
                invalid.append(feature)
            validated[feature] = value

        if invalid:
            return None, invalid

        return validated, []

    def _collect_voice_features(self):
        voice_events = []

        if not self.voice_session_data:
            self._warn_measurement("voice", "voice recording was not started or no voice session data was attached")
            return self._none_features("voice"), voice_events

        if self.voice_session_data.get("error"):
            self._warn_measurement("voice", self.voice_session_data["error"])
            return self._none_features("voice"), self.voice_session_data.get("events", [])

        voice_summary = self.voice_session_data.get("summary") or {}
        voice_events = self.voice_session_data.get("events", [])
        voice_features, invalid = self._validate_modality_features(
            "voice",
            voice_summary
        )

        if voice_features is None:
            self._warn_measurement(
                "voice",
                f"invalid or missing voice feature values: {', '.join(invalid)}"
            )
            return self._none_features("voice"), voice_events

        return voice_features, voice_events

    def _collect_eye_features(self):
        try:
            raw_eye_features = {
                "fixation_duration": self.get_fixation_duration(),
                "fixation_count": self.get_fixation_count(),
                "saccade_count": self.get_saccade_count(),
            }
        except Exception as exc:
            self._warn_measurement("eye", f"eye tracking measurement failed: {exc}")
            return self._none_features("eye")

        eye_features, invalid = self._validate_modality_features(
            "eye",
            raw_eye_features
        )

        if eye_features is None:
            self._warn_measurement(
                "eye",
                f"eye tracker missing, script inactive, or invalid values: {', '.join(invalid)}"
            )
            return self._none_features("eye")

        return eye_features

    def _collect_game_features(self):
        fg_score = self._try_get_latest_flightgear_score()
        score = self._coerce_valid_number("game", "score", fg_score)

        if score is None:
            if fg_score is None:
                self._warn_measurement("game", "game was not started or no FlightGear score was found")
            else:
                self._warn_measurement("game", f"invalid game score value: {fg_score}")
            return self._none_features("game")

        return {"score": score}

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
        quality_warning = self._build_quality_warning()

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
            "raw_score": raw.get("raw_score"),
            "modality_contributions": raw.get(
                "modality_contributions",
                {}
            ),
            "measurement_warnings": self.measurement_warnings.copy(),
            "quality_warning": quality_warning,
            "features": self.features,
            "baseline": b
        })

        return self.result

    def _build_quality_warning(self):
        labels = []
        for warning in self.measurement_warnings:
            label = warning["label"]
            if label not in labels:
                labels.append(label)

        if not labels:
            return None

        return (
            "איכות ציון העייפות נמוכה עקב חוסר מדידה תקינה של "
            + " / ".join(labels)
        )

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
            "measurement_warnings": self.measurement_warnings.copy(),
            "quality_warning": self._build_quality_warning(),
            "features": self.features,
            "baseline": (
                self.subject.get("baseline")
                if self.subject
                else {}
            )
        }
