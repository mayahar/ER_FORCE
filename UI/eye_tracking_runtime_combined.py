"""Combined eye runtime for Tobii Pro Glasses 3 and screen-mounted Tobii bar."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from core.hardware_config import (
    bar_head_position_enabled,
    calibrate_bar,
    calibrate_glasses,
    combined_eye_results_source,
)
from core.session_manager import (
    eye_tracker_calibration_status_from_runtime,
    update_session_metadata,
)
from score.eye_features import apply_controller_eye_features, has_eye_features

SKIP_EYE_CALIBRATION = False


class _ControllerView:
    def __init__(self, controller: Any | None, eye_dir: Path | None):
        self._controller = controller
        self._eye_features = None
        self.subject = getattr(controller, "subject", None)
        self.session = self._session_with_eye_dir(getattr(controller, "session", None), eye_dir)

    @staticmethod
    def _session_with_eye_dir(session: Any | None, eye_dir: Path | None):
        if session is None or eye_dir is None:
            return session
        try:
            return replace(session, eye_dir=eye_dir)
        except Exception:
            pass
        values = dict(getattr(session, "__dict__", {}) or {})
        values["eye_dir"] = eye_dir
        return type("SessionView", (), values)()

    def set_eye_features(self, eye_features: dict | None) -> None:
        self._eye_features = eye_features


class EyeTrackingRuntime:
    def __init__(self):
        from UI.eye_tracking_runtime_glasses import EyeTrackingRuntime as GlassesRuntime

        self.glasses = GlassesRuntime()
        self.bar = None
        self.selected_eye_source = combined_eye_results_source()
        self.all_eye_features: dict[str, dict[str, Any] | None] = {
            "glasses": None,
            "bar": None,
        }
        self.last_error = ""
        self.export_paths = None
        self.raw_sample_count = 0
        self.tracker_connected = False
        self.tracker_label = "Tobii Pro Glasses 3 + Tobii bar"
        self.calibration_passed = False
        self.calibration_message = ""
        self.calibration_preview_path = None
        self.calibration_attempted = False
        self.calibration_summary = None
        self.current_recording_uuid = None
        self.active_host = None
        self.active = False
        self.recording_started_at = None
        self.session_eye_dir: Path | None = None
        self.glasses_eye_dir: Path | None = None
        self.bar_eye_dir: Path | None = None

    def _ensure_bar_runtime(self):
        if self.bar is None:
            from UI.eye_tracking_runtime_bar import EyeTrackingRuntime as BarRuntime

            self.bar = BarRuntime()
        return self.bar

    def configure_session(self, controller: Any | None = None) -> None:
        session = getattr(controller, "session", None)
        eye_dir = getattr(session, "eye_dir", None)
        self.session_eye_dir = Path(eye_dir) if eye_dir else None
        if self.session_eye_dir is None:
            return

        self.glasses_eye_dir = Path(
            getattr(session, "glasses_eye_dir", None) or self.session_eye_dir / "glasses"
        )
        self.bar_eye_dir = Path(
            getattr(session, "bar_eye_dir", None) or self.session_eye_dir / "bar"
        )
        self.glasses_eye_dir.mkdir(parents=True, exist_ok=True)
        self.bar_eye_dir.mkdir(parents=True, exist_ok=True)

        self.glasses.configure_session(_ControllerView(controller, self.glasses_eye_dir))
        self._ensure_bar_runtime().configure_session(_ControllerView(controller, self.bar_eye_dir))

    def start_preview(self, *_args, **_kwargs) -> bool:
        return True

    def stop_preview(self) -> None:
        return None

    def ensure_tracker(self) -> tuple[bool, str]:
        glasses_ok = self.glasses.ensure_tracker()
        if isinstance(glasses_ok, tuple):
            glasses_ok, glasses_error = bool(glasses_ok[0]), str(glasses_ok[1] or "")
        else:
            glasses_ok, glasses_error = bool(glasses_ok), getattr(self.glasses, "last_error", "")

        bar = self._ensure_bar_runtime()
        bar_result = bar.ensure_tracker()
        if isinstance(bar_result, tuple):
            bar_ok, bar_error = bool(bar_result[0]), str(bar_result[1] or "")
        else:
            bar_ok, bar_error = bool(bar_result), getattr(bar, "last_error", "")

        self.tracker_connected = glasses_ok and bar_ok
        self.last_error = "; ".join(error for error in (glasses_error, bar_error) if error)
        self._sync_public_state()
        return self.tracker_connected, self.last_error

    def run_calibration(self, parent=None, screen=None, controller=None) -> tuple[bool, str]:
        self.configure_session(controller)
        self.calibration_attempted = True
        self._write_flow_log("combined_calibration_start")

        if calibrate_glasses():
            from UI.eye_calibration_glasses import run_eye_calibration as run_glasses_calibration

            glasses_success, glasses_message, glasses_preview = run_glasses_calibration(
                runtime=self.glasses,
                parent=parent,
                screen=screen,
            )
            self._write_flow_log(f"glasses_calibration_returned: success={glasses_success}")
            if hasattr(self.glasses, "calibration_preview_path"):
                self.glasses.calibration_preview_path = glasses_preview
        else:
            glasses_success = True
            glasses_message = "glasses calibration skipped"
            self.glasses.calibration_attempted = False
            self.glasses.calibration_passed = True
            self.glasses.calibration_message = glasses_message
            self._write_flow_log("glasses_calibration_skipped")

        import UI.eye_calibration_bar as bar_calibration

        bar = self._ensure_bar_runtime()
        if calibrate_bar():
            bar_calibration.HEAD_POSITION_ENABLED = bar_head_position_enabled()
            self._write_flow_log("bar_calibration_start")
            try:
                bar_success, bar_message = bar.run_calibration(
                    parent=parent,
                    screen=screen,
                    controller=_ControllerView(controller, self.bar_eye_dir),
                )
                self._write_flow_log(f"bar_calibration_returned: success={bar_success}")
            except Exception as exc:
                bar_success = False
                bar_message = str(exc)
                self._write_flow_log(f"bar_calibration_exception: {exc}")
        else:
            bar_success = True
            bar_message = "bar calibration skipped"
            bar.calibration_attempted = False
            bar.calibration_passed = True
            bar.calibration_message = bar_message
            self._write_flow_log("bar_calibration_skipped")

        messages = []
        if glasses_success:
            messages.append("glasses calibration completed")
        else:
            messages.append(f"glasses calibration did not confirm success: {glasses_message}")
        if bar_success:
            messages.append("bar calibration completed")
        else:
            messages.append(f"bar calibration did not confirm success: {bar_message}")
        selected_success = (
            bool(glasses_success)
            if self.selected_eye_source == "glasses"
            else bool(bar_success)
        )
        self.calibration_passed = selected_success
        self.calibration_message = "; ".join(messages)
        self.last_error = "" if selected_success else self.calibration_message
        self._sync_public_state()
        try:
            self._write_combined_calibration_record()
            self._write_flow_log("combined_calibration_record_written")
        except Exception as exc:
            self._write_flow_log(f"combined_calibration_record_error: {exc}")
        return selected_success, self.calibration_message

    def start(self, camera_index: int = 0, subject_id: str | None = None) -> tuple[bool, str]:
        self.last_error = ""
        errors = {}

        glasses_ok, glasses_error = self._call_start(self.glasses, camera_index, subject_id)
        if glasses_error:
            errors["glasses"] = glasses_error

        bar_ok, bar_error = self._call_start(self._ensure_bar_runtime(), camera_index, subject_id)
        if bar_error:
            errors["bar"] = bar_error

        self.active = bool(glasses_ok or bar_ok)
        self.last_error = "; ".join(f"{name}: {error}" for name, error in errors.items())
        self._sync_public_state()
        selected_ok = glasses_ok if self.selected_eye_source == "glasses" else bar_ok
        return bool(selected_ok), "" if selected_ok else self.last_error

    @staticmethod
    def _call_start(runtime, camera_index: int, subject_id: str | None) -> tuple[bool, str]:
        try:
            result = runtime.start(camera_index, subject_id)
        except TypeError:
            result = runtime.start()
        if isinstance(result, tuple):
            return bool(result[0]), str(result[1] or "")
        return bool(result), ""

    def stop(self, controller: Any | None = None) -> tuple[dict[str, Any] | None, str]:
        self.configure_session(controller)
        features = {}
        errors = {}

        for source, runtime, eye_dir in (
            ("glasses", self.glasses, self.glasses_eye_dir),
            ("bar", self._ensure_bar_runtime(), self.bar_eye_dir),
        ):
            view = _ControllerView(controller, eye_dir)
            try:
                source_features, source_error = runtime.stop(view)
            except Exception as exc:
                source_features, source_error = None, str(exc)
            features[source] = source_features
            if source_error:
                errors[source] = source_error

        self.all_eye_features = features
        selected_features = features.get(self.selected_eye_source)
        if not has_eye_features(selected_features):
            fallback_source = "bar" if self.selected_eye_source == "glasses" else "glasses"
            if has_eye_features(features.get(fallback_source)):
                selected_features = features[fallback_source]
                self.last_error = (
                    f"{self.selected_eye_source} eye features were unavailable; "
                    f"using {fallback_source} for final scoring."
                )
            else:
                self.last_error = "; ".join(f"{name}: {error}" for name, error in errors.items())
        else:
            self.last_error = "; ".join(
                f"{name}: {error}"
                for name, error in errors.items()
                if name != self.selected_eye_source
            )

        apply_controller_eye_features(controller, selected_features)
        self._sync_public_state()
        self._write_combined_record()
        return selected_features, self.last_error

    def save_pending_raw_gaze_async(self) -> None:
        for runtime in (self.glasses, self.bar):
            if runtime is None:
                continue
            if hasattr(runtime, "save_pending_raw_gaze_async"):
                runtime.save_pending_raw_gaze_async()
        self._sync_public_state()

    def reset(self) -> None:
        self.glasses.reset()
        if self.bar is not None:
            self.bar.reset()
        self.all_eye_features = {"glasses": None, "bar": None}
        self.last_error = ""
        self.export_paths = None
        self.raw_sample_count = 0
        self.active = False
        self._sync_public_state()

    def reset_calibration(self) -> None:
        self.glasses.reset_calibration()
        if self.bar is not None:
            self.bar.reset_calibration()
        self.calibration_passed = False
        self.calibration_message = ""
        self.calibration_preview_path = None
        self.calibration_attempted = False
        self.calibration_summary = None

    def _sync_public_state(self) -> None:
        self.export_paths = {
            "glasses": getattr(self.glasses, "export_paths", None),
            "bar": getattr(self.bar, "export_paths", None),
        }
        self.raw_sample_count = int(getattr(self.glasses, "raw_sample_count", 0) or 0)
        self.raw_sample_count += int(getattr(self.bar, "raw_sample_count", 0) or 0)
        self.current_recording_uuid = getattr(self.glasses, "current_recording_uuid", None)
        self.active_host = getattr(self.glasses, "active_host", None)
        self.recording_started_at = getattr(self.glasses, "recording_started_at", None)
        self.calibration_preview_path = getattr(self.glasses, "calibration_preview_path", None)
        self.calibration_summary = {
            "selected_eye_source": self.selected_eye_source,
            "glasses": getattr(self.glasses, "calibration_summary", None),
            "bar": getattr(self.bar, "calibration_summary", None) if self.bar is not None else None,
        }

    def _write_combined_calibration_record(self) -> None:
        if self.session_eye_dir is None:
            return
        payload = {
            "mode": "combined",
            "selected_eye_source": self.selected_eye_source,
            "completed_at": datetime.now().isoformat(timespec="seconds"),
            "passed": bool(self.calibration_passed),
            "message": self.calibration_message,
            "glasses": {
                "attempted": bool(getattr(self.glasses, "calibration_attempted", False)),
                "passed": bool(getattr(self.glasses, "calibration_passed", False)),
                "message": getattr(self.glasses, "calibration_message", ""),
                "directory": str(self.glasses_eye_dir) if self.glasses_eye_dir else None,
            },
            "bar": {
                "attempted": bool(getattr(self.bar, "calibration_attempted", False)) if self.bar is not None else False,
                "passed": bool(getattr(self.bar, "calibration_passed", False)) if self.bar is not None else False,
                "message": getattr(self.bar, "calibration_message", "") if self.bar is not None else "",
                "directory": str(self.bar_eye_dir) if self.bar_eye_dir else None,
                "head_position_enabled": bar_head_position_enabled(),
            },
        }
        path = self.session_eye_dir / "combined_calibration.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        session = None
        if self.session_eye_dir is not None:
            session = type("SessionView", (), {"root": self.session_eye_dir.parent})()
        update_session_metadata(
            session,
            {
                "eye_tracker_calibration_status": (
                    eye_tracker_calibration_status_from_runtime(self)
                )
            },
        )

    def _write_flow_log(self, message: str) -> None:
        if self.session_eye_dir is None:
            return
        try:
            path = self.session_eye_dir.parent / "startup_flow.log"
            previous = path.read_text(encoding="utf-8") if path.exists() else ""
            path.write_text(previous + f"{datetime.now().isoformat(timespec='seconds')} {message}\n", encoding="utf-8")
        except Exception:
            pass

    def _write_combined_record(self) -> None:
        if self.session_eye_dir is None:
            return
        payload = {
            "mode": "combined",
            "selected_eye_source": self.selected_eye_source,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "directories": {
                "glasses": str(self.glasses_eye_dir) if self.glasses_eye_dir else None,
                "bar": str(self.bar_eye_dir) if self.bar_eye_dir else None,
            },
            "export_paths": self.export_paths,
            "raw_sample_count": {
                "glasses": getattr(self.glasses, "raw_sample_count", 0),
                "bar": getattr(self.bar, "raw_sample_count", 0) if self.bar is not None else 0,
            },
            "features": self.all_eye_features,
        }
        path = self.session_eye_dir / "combined_eye_recording.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
