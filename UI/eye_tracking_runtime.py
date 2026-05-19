"""Eye tracking session helpers for the PySide game screen."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from eye_tracking_analysis.eye_movement_analyzer import EyeMovementAnalyzer
from eye_tracking_analysis.eye_tracker_recorder import EyeTrackerRecorder
from eye_tracking_analysis.gaze_raw_export import (
    export_eye_session_recording,
    export_raw_gaze_recording,
)
from score.eye_features import apply_controller_eye_features

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RECORDINGS_DIR = REPO_ROOT / "eye_tracking_analysis" / "recordings"


class EyeTrackingRuntime:
    def __init__(self):
        self.recorder: EyeTrackerRecorder | None = None
        self.analyzer: EyeMovementAnalyzer | None = None
        self.active = False
        self.last_error = ""
        self.export_paths: dict[str, str] | None = None
        self.raw_sample_count = 0
        self.tracker_connected = False
        self.tracker_label = ""
        self.calibration_passed = False
        self.calibration_message = ""
        self.calibration_preview_path: str | None = None

    def _ensure(self) -> None:
        if self.recorder is None:
            self.recorder = EyeTrackerRecorder()
        if self.analyzer is None:
            self.analyzer = EyeMovementAnalyzer()

    def reset(self) -> None:
        self.active = False
        self.last_error = ""
        self.export_paths = None
        self.raw_sample_count = 0

    def reset_calibration(self) -> None:
        self.calibration_passed = False
        self.calibration_message = ""
        self.calibration_preview_path = None

    def ensure_tracker(self) -> tuple[bool, str]:
        self._ensure()
        if self.recorder is None:
            self.tracker_connected = False
            self.tracker_label = ""
            return False, "Eye tracker recorder is unavailable."

        if self.recorder.eyetracker is not None:
            self.tracker_connected = True
            model = getattr(self.recorder.eyetracker, "model", "Tobii")
            serial = getattr(self.recorder.eyetracker, "serial_number", "")
            self.tracker_label = f"{model} ({serial})" if serial else str(model)
            return True, ""

        if not self.recorder.find_and_select_eyetracker(auto_select_first=True):
            self.tracker_connected = False
            self.tracker_label = ""
            return False, "לא נמצא עוקב עיניים."

        self.tracker_connected = True
        model = getattr(self.recorder.eyetracker, "model", "Tobii")
        serial = getattr(self.recorder.eyetracker, "serial_number", "")
        self.tracker_label = f"{model} ({serial})" if serial else str(model)
        return True, ""

    def run_calibration(
        self,
        parent=None,
        screen=None,
        controller=None,
    ) -> tuple[bool, str]:
        from .eye_calibration import run_eye_calibration

        connected, error = self.ensure_tracker()
        if not connected:
            self.calibration_passed = False
            self.calibration_message = error
            return False, error

        save_dir = None
        session = getattr(controller, "session", None) if controller else None
        if session is not None and getattr(session, "eye_dir", None):
            save_dir = Path(session.eye_dir)

        success, message, _preview = run_eye_calibration(
            self.recorder.eyetracker,
            parent=parent,
            screen=screen,
            save_dir=save_dir,
        )
        self.calibration_passed = success
        self.calibration_message = message
        self.calibration_preview_path = None
        if not success:
            self.last_error = message
        else:
            if save_dir is not None:
                preview_file = save_dir / "calibration_fixation_map.png"
                if preview_file.is_file():
                    self.calibration_preview_path = str(preview_file)
            self._save_calibration_record(controller, message)
        return success, message

    def _save_calibration_record(self, controller, message: str) -> None:
        session = getattr(controller, "session", None) if controller else None
        if session is None or not getattr(session, "eye_dir", None):
            return
        eye_dir = Path(session.eye_dir)
        eye_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "passed": True,
            "message": message,
            "tracker": self.tracker_label,
            "completed_at": datetime.now().isoformat(timespec="seconds"),
            "points": 5,
        }
        (eye_dir / "calibration.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def start(self) -> tuple[bool, str]:
        if self.active:
            return True, ""

        self.last_error = ""
        self.export_paths = None
        self.raw_sample_count = 0
        self._ensure()

        if self.recorder is None:
            return False, "Eye tracker recorder is unavailable."

        if self.recorder.eyetracker is None:
            if not self.recorder.find_and_select_eyetracker(auto_select_first=True):
                return False, "לא נמצא עוקב עיניים. המשחק ימשיך בלי הקלטת עיניים."
            self.tracker_connected = True

        if not self.recorder.start_recording():
            return False, "שגיאה בהפעלה של הקלטת תנועות העיניים."

        self.active = True
        return True, ""

    def stop(self, controller=None) -> tuple[dict[str, Any] | None, str]:
        self.active = False
        self.export_paths = None
        self.raw_sample_count = 0

        if self.recorder is None:
            apply_controller_eye_features(controller, None)
            return None, ""

        was_active = bool(self.recorder.is_recording)
        if self.recorder.is_recording and not self.recorder.stop_recording():
            gaze_data = self.recorder.get_collected_data()
            if not gaze_data:
                self.last_error = "שגיאה בהפסקת הקלטת תנועות העיניים."
                apply_controller_eye_features(controller, None)
                return None, self.last_error

        gaze_data = self.recorder.get_collected_data()
        sample_count = len(gaze_data)
        self.raw_sample_count = sample_count

        if sample_count == 0:
            self.last_error = "לא נאספו נתוני עיניים (0 דגימות מהמכשיר)."
            apply_controller_eye_features(controller, None)
            if was_active:
                return None, self.last_error
            return None, ""

        output_dir = DEFAULT_RECORDINGS_DIR
        subject_id = None
        session_id = None
        if controller is not None:
            if getattr(controller, "subject", None):
                subject_id = controller.subject.get("id")
            session = getattr(controller, "session", None)
            if session is not None:
                session_id = getattr(session, "session_id", None)
                if getattr(session, "eye_dir", None):
                    output_dir = Path(session.eye_dir)

        features, fixations, saccades, metrics, analyze_error = self._analyze_gaze(
            gaze_data
        )

        try:
            export_result = export_eye_session_recording(
                self.recorder,
                output_dir=output_dir,
                subject_id=subject_id,
                session_id=session_id,
                features=features,
                fixations=fixations,
                saccades=saccades,
                metrics=metrics,
            )
            self.export_paths = {
                key: str(path)
                for key, path in export_result.items()
                if key != "sample_count" and key != "directory"
            }
            self.export_paths["directory"] = str(export_result["directory"])
            self.raw_sample_count = int(export_result["sample_count"])
        except Exception as exc:
            try:
                raw_export = export_raw_gaze_recording(
                    self.recorder,
                    output_dir=output_dir,
                    subject_id=subject_id,
                    session_id=session_id,
                )
                self.export_paths = {
                    key: str(path)
                    for key, path in raw_export.items()
                    if key != "sample_count" and key != "directory"
                }
                self.export_paths["directory"] = str(raw_export["directory"])
                self.raw_sample_count = int(raw_export["sample_count"])
            except Exception as raw_exc:
                self.last_error = (
                    f"שמירת נתוני עיניים נכשלה: {exc}; raw export also failed: {raw_exc}"
                )
                apply_controller_eye_features(controller, None)
                return None, self.last_error

            self.last_error = (
                f"שגיאה בשמירת תוצאות אנליזת עיניים: {exc}; שמרנו נתוני גייס גולמיים בלבד."
            )
            apply_controller_eye_features(controller, None)
            return None, self.last_error

        if analyze_error:
            self.last_error = analyze_error
            apply_controller_eye_features(controller, None)
            return None, analyze_error

        apply_controller_eye_features(controller, features)
        return features, ""

    def _analyze_gaze(self, gaze_data):
        eye_x = []
        eye_y = []
        timestamps = []

        for sample in gaze_data:
            x = sample.left_x if sample.left_x is not None else sample.right_x
            y = sample.left_y if sample.left_y is not None else sample.right_y
            eye_x.append(np.nan if x is None else x)
            eye_y.append(np.nan if y is None else y)
            timestamps.append(sample.timestamp)

        timestamps = np.array(timestamps, dtype=float)
        if timestamps.size == 0:
            return None, None, None, None, "אין חיווי זמן תקני בנתוני העין."

        if np.nanmax(timestamps) > 1e5:
            timestamps = timestamps / 1_000_000
        timestamps = timestamps - timestamps[0]

        gaze_x = np.array(eye_x, dtype=float)
        gaze_y = np.array(eye_y, dtype=float)

        if self.analyzer is None:
            return None, None, None, None, "אנלייזר של תנועות עיניים אינו זמין."

        try:
            fixations, saccades, metrics = self.analyzer.analyze_gaze_data(
                gaze_x=gaze_x,
                gaze_y=gaze_y,
                timestamps=timestamps,
            )
        except Exception as exc:
            return None, None, None, None, f"ניתוח תנועות העיניים נכשל: {exc}"

        if metrics is None:
            return None, None, None, None, "לא ניתן לחשב מדדים מתנועות העיניים."

        features = {
            "fixation_duration": float(metrics.mean_fixation_duration),
            "fixation_count": int(metrics.num_fixations),
            "saccade_count": int(metrics.num_saccades),
            "analysis": {
                "total_duration": float(metrics.total_duration),
                "fixations_per_minute": float(metrics.fixations_per_minute),
                "saccades_per_minute": float(metrics.saccades_per_minute),
                "mean_fixation_duration": float(metrics.mean_fixation_duration),
                "mean_saccade_velocity": float(metrics.mean_saccade_velocity),
            },
        }
        return features, fixations, saccades, metrics, ""

    def _analyze_gaze(self, gaze_data):
        eye_x = []
        eye_y = []
        timestamps = []

        for sample in gaze_data:
            x = sample.left_x if sample.left_x is not None else sample.right_x
            y = sample.left_y if sample.left_y is not None else sample.right_y
            eye_x.append(np.nan if x is None else x)
            eye_y.append(np.nan if y is None else y)
            timestamps.append(sample.timestamp)

        timestamps = np.array(timestamps, dtype=float)
        if timestamps.size == 0:
            return None, None, None, None, "No valid timestamps in eye data."

        if np.nanmax(timestamps) > 1e5:
            timestamps = timestamps / 1_000_000
        timestamps = timestamps - timestamps[0]

        gaze_x = np.array(eye_x, dtype=float)
        gaze_y = np.array(eye_y, dtype=float)

        if self.analyzer is None:
            return None, None, None, None, "Eye movement analyzer is unavailable."

        try:
            analysis_result = self.analyzer.analyze_gaze_data(
                gaze_x=gaze_x,
                gaze_y=gaze_y,
                timestamps=timestamps,
            )
        except Exception as exc:
            return None, None, None, None, f"Eye movement analysis failed: {exc}"

        fixations = None
        saccades = None
        metrics = analysis_result
        if isinstance(analysis_result, tuple):
            if len(analysis_result) == 3:
                fixations, saccades, metrics = analysis_result
            else:
                return None, None, None, None, "Unsupported eye analysis result format."

        if metrics is None:
            return None, None, None, None, "Could not compute eye movement metrics."

        fixation_duration = self._metric_value(
            metrics,
            "fixation_duration",
            "mean_fixation_duration",
        )
        fixation_count = self._metric_value(
            metrics,
            "fixation_count",
            "num_fixations",
        )
        saccade_count = self._metric_value(
            metrics,
            "saccade_count",
            "num_saccades",
        )
        total_duration = float(timestamps[-1] - timestamps[0]) if timestamps.size > 1 else 0.0

        features = {
            "fixation_duration": float(fixation_duration),
            "fixation_count": float(fixation_count),
            "saccade_count": float(saccade_count),
            "analysis": {
                "total_duration": self._metric_value(
                    metrics,
                    "total_duration",
                    default=total_duration,
                ),
                "fixations_per_minute": float(fixation_count),
                "saccades_per_minute": float(saccade_count),
                "fixation_duration_per_minute": float(fixation_duration),
                "mean_fixation_duration": self._metric_value(
                    metrics,
                    "mean_fixation_duration",
                ),
                "mean_saccade_velocity": self._metric_value(
                    metrics,
                    "mean_saccade_velocity",
                ),
            },
        }
        return features, fixations, saccades, metrics, ""

    @staticmethod
    def _metric_value(metrics, *names, default=0.0) -> float:
        for name in names:
            if hasattr(metrics, name):
                try:
                    value = float(getattr(metrics, name))
                except (TypeError, ValueError):
                    continue
                if np.isfinite(value):
                    return value
        return float(default)
