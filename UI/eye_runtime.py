"""Lazy compatibility wrapper for the PySide game screen eye runtime calls."""


def get_camera_index() -> int:
    return 0


class EyeTrackingRuntime:
    def __init__(self):
        self._runtime = None
        self.last_error = ""
        self.export_paths = None
        self.raw_sample_count = 0
        self.tracker_connected = False
        self.tracker_label = ""
        self.calibration_passed = False
        self.calibration_message = ""
        self.calibration_preview_path = None

    def _ensure_runtime(self):
        if self._runtime is None:
            from ui.eye_tracking_runtime import EyeTrackingRuntime as TobiiEyeTrackingRuntime

            runtime = TobiiEyeTrackingRuntime()
            runtime.last_error = self.last_error
            runtime.export_paths = self.export_paths
            runtime.raw_sample_count = self.raw_sample_count
            runtime.tracker_connected = self.tracker_connected
            runtime.tracker_label = self.tracker_label
            runtime.calibration_passed = self.calibration_passed
            runtime.calibration_message = self.calibration_message
            runtime.calibration_preview_path = self.calibration_preview_path
            self._runtime = runtime
        return self._runtime

    def _sync_from_runtime(self):
        if self._runtime is None:
            return
        for name in (
            "last_error",
            "export_paths",
            "raw_sample_count",
            "tracker_connected",
            "tracker_label",
            "calibration_passed",
            "calibration_message",
            "calibration_preview_path",
        ):
            setattr(self, name, getattr(self._runtime, name, getattr(self, name)))

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)
        runtime = self.__dict__.get("_runtime")
        if runtime is not None and name != "_runtime" and hasattr(runtime, name):
            setattr(runtime, name, value)

    def start_preview(self, _camera_index=0, _on_frame=None) -> bool:
        return True

    def stop_preview(self) -> None:
        return None

    def start_recording(self, _camera_index=0, _subject_id=None) -> bool:
        ok, error = self._ensure_runtime().start()
        self._sync_from_runtime()
        self.last_error = error
        return ok

    def stop_recording(self, controller=None):
        features, error = self._ensure_runtime().stop(controller)
        self._sync_from_runtime()
        self.last_error = error
        return features

    def ensure_tracker(self):
        result = self._ensure_runtime().ensure_tracker()
        self._sync_from_runtime()
        return result

    def run_calibration(self, *args, **kwargs):
        result = self._ensure_runtime().run_calibration(*args, **kwargs)
        self._sync_from_runtime()
        return result

    def reset(self) -> None:
        if self._runtime is not None:
            self._runtime.reset()
            self._sync_from_runtime()
        else:
            self.last_error = ""
            self.export_paths = None
            self.raw_sample_count = 0

    def reset_calibration(self) -> None:
        if self._runtime is not None:
            self._runtime.reset_calibration()
            self._sync_from_runtime()
        else:
            self.calibration_passed = False
            self.calibration_message = ""
            self.calibration_preview_path = None
