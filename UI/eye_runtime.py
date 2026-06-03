"""Compatibility wrapper for the PySide eye runtime calls."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from typing import Any, Callable

from core.hardware_config import using_glasses


def get_camera_index() -> int:
    """The selected runtime keeps the public camera-index API stable."""
    return 0


class EyeTrackingRuntime:
    """Keep the UI-facing API stable while delegating to the configured runtime."""

    def __init__(self):
        self._runtime = None
        self.last_error = ""
        self.export_paths = None
        self.raw_sample_count = 0
        self.tracker_connected = False
        self.tracker_label = "Tobii Pro Glasses 3" if using_glasses() else ""
        self.calibration_passed = False
        self.calibration_message = ""
        self.calibration_preview_path = None
        self.calibration_attempted = False
        self.calibration_summary = None
        self.current_recording_uuid = None
        self.active_host = None
        self.active = False
        self.recording_started_at = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._start_future: Future | None = None

    def _ensure_runtime(self):
        if self._runtime is None:
            if using_glasses():
                from ui.eye_tracking_runtime_glasses import EyeTrackingRuntime as Runtime
            else:
                from ui.eye_tracking_runtime_bar import EyeTrackingRuntime as Runtime

            runtime = Runtime()
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
            "calibration_summary",
            "current_recording_uuid",
            "active_host",
            "active",
            "recording_started_at",
        )

    def configure_session(self, controller=None) -> None:
        runtime = self._ensure_runtime()
        if hasattr(runtime, "configure_session"):
            runtime.configure_session(controller)
        self._sync_from_runtime()

    def start_preview(
        self,
        _camera_index: int = 0,
        _on_frame: Callable[[Any], None] | None = None,
    ) -> bool:
        return True

    def stop_preview(self) -> None:
        return None

    def start_recording(self, camera_index: int = 0, subject_id: str | None = None) -> bool:
        runtime = self._ensure_runtime()
        try:
            result = runtime.start(camera_index, subject_id)
        except TypeError:
            result = runtime.start()
        ok, error = self._split_ok_error(result)
        self._sync_from_runtime()
        self.last_error = error
        return ok

    def start_recording_async(self, camera_index: int = 0, subject_id: str | None = None) -> Future:
        if self._start_future is not None and not self._start_future.done():
            return self._start_future
        self._start_future = self._executor.submit(self.start_recording, camera_index, subject_id)
        return self._start_future

    def poll_start_recording(self) -> bool | None:
        if self._start_future is None or not self._start_future.done():
            return None
        try:
            return bool(self._start_future.result())
        finally:
            self._sync_from_runtime()

    def wait_for_start_recording(self, timeout: float | None = None) -> bool:
        if self._start_future is None:
            return bool(self.active)
        try:
            return bool(self._start_future.result(timeout=timeout))
        except TimeoutError:
            self.last_error = (
                "Tobii glasses connection is still in progress"
                if using_glasses()
                else "Tobii bar connection is still in progress"
            )
            return False
        finally:
            self._sync_from_runtime()

    def stop_recording(self, controller=None):
        if not self.wait_for_start_recording(timeout=20.0):
            return None
        features, error = self._ensure_runtime().stop(controller)
        self._sync_from_runtime()
        self.last_error = error
        return features

    def save_pending_raw_gaze_async(self) -> None:
        runtime = self._ensure_runtime()
        if hasattr(runtime, "save_pending_raw_gaze_async"):
            runtime.save_pending_raw_gaze_async()
        self._sync_from_runtime()

    def ensure_tracker(self) -> bool:
        result = self._ensure_runtime().ensure_tracker()
        ok, error = self._split_ok_error(result)
        self._sync_from_runtime()
        if error:
            self.last_error = error
        return ok

    def run_calibration(self, *args, **kwargs) -> tuple[bool, str]:
        runtime = self._ensure_runtime()
        controller = kwargs.get("controller")
        if controller is not None and hasattr(runtime, "configure_session"):
            runtime.configure_session(controller)
        if hasattr(runtime, "run_calibration") and not using_glasses():
            result = runtime.run_calibration(*args, **kwargs)
            success, message = self._split_ok_error(result)
        else:
            from ui.eye_calibration import run_eye_calibration

            success, message, preview = run_eye_calibration(
                runtime,
                *args,
                **kwargs,
            )
            if hasattr(runtime, "calibration_preview_path"):
                runtime.calibration_preview_path = preview
            if hasattr(runtime, "calibration_attempted"):
                runtime.calibration_attempted = True
        self._sync_from_runtime()
        return success, message

    @staticmethod
    def _split_ok_error(result) -> tuple[bool, str]:
        if isinstance(result, tuple):
            ok = bool(result[0]) if result else False
            error = str(result[1]) if len(result) > 1 and result[1] else ""
            return ok, error
        return bool(result), ""

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
        self.calibration_preview_path = None
        self.calibration_attempted = False
        self.calibration_summary = None
