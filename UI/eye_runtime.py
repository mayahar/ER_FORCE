"""Compatibility wrapper for the PySide eye runtime calls."""

from __future__ import annotations

from typing import Any, Callable


def get_camera_index() -> int:
    """The Tobii Glasses 3 flow does not use a local camera index."""
    return 0


class EyeTrackingRuntime:
    """Keep the UI-facing API stable while delegating to the glasses runtime."""

    def __init__(self):
        self._runtime = None
        self.last_error = ""
        self.export_paths = None
        self.raw_sample_count = 0
        self.tracker_connected = False
        self.tracker_label = "Tobii Pro Glasses 3"
        self.calibration_passed = False
        self.calibration_message = ""
        self.calibration_preview_path = None
        self.calibration_attempted = False
        self.current_recording_uuid = None
        self.active_host = None
        self.active = False

    def _ensure_runtime(self):
        if self._runtime is None:
            from ui.eye_tracking_runtime import EyeTrackingRuntime as TobiiEyeTrackingRuntime

            runtime = TobiiEyeTrackingRuntime()
            self._copy_state_to(runtime)
            self._runtime = runtime
        return self._runtime

    def _copy_state_to(self, runtime) -> None:
        for name in self._state_names():
            if hasattr(runtime, name):
                setattr(runtime, name, getattr(self, name))

    def _sync_from_runtime(self) -> None:
        if self._runtime is None:
            return
        for name in self._state_names():
            if hasattr(self._runtime, name):
                setattr(self, name, getattr(self._runtime, name))

    @staticmethod
    def _state_names() -> tuple[str, ...]:
        return (
            "last_error",
            "export_paths",
            "raw_sample_count",
            "tracker_connected",
            "tracker_label",
            "calibration_passed",
            "calibration_message",
            "calibration_preview_path",
            "calibration_attempted",
            "current_recording_uuid",
            "active_host",
            "active",
        )

    def start_preview(
        self,
        _camera_index: int = 0,
        _on_frame: Callable[[Any], None] | None = None,
    ) -> bool:
        return True

    def stop_preview(self) -> None:
        return None

    def start_recording(self, camera_index: int = 0, subject_id: str | None = None) -> bool:
        ok, error = self._ensure_runtime().start(camera_index, subject_id)
        self._sync_from_runtime()
        self.last_error = error
        return ok

    def stop_recording(self, controller=None):
        features, error = self._ensure_runtime().stop(controller)
        self._sync_from_runtime()
        self.last_error = error
        return features

    def ensure_tracker(self) -> bool:
        ok = self._ensure_runtime().ensure_tracker()
        self._sync_from_runtime()
        return ok

    def run_calibration(self, *args, **kwargs) -> tuple[bool, str]:
        from ui.eye_calibration import run_eye_calibration

        success, message, preview = run_eye_calibration(
            self._ensure_runtime(),
            *args,
            **kwargs,
        )
        runtime = self._ensure_runtime()
        runtime.calibration_preview_path = preview
        runtime.calibration_attempted = True
        self._sync_from_runtime()
        return success, message

    def reset(self) -> None:
        if self._runtime is not None:
            self._runtime.reset()
            self._sync_from_runtime()
            return

        self.last_error = ""
        self.export_paths = None
        self.raw_sample_count = 0

    def reset_calibration(self) -> None:
        if self._runtime is not None:
            self._runtime.reset_calibration()
            self._sync_from_runtime()
            return

        self.calibration_passed = False
        self.calibration_message = ""
        self.calibration_attempted = False
