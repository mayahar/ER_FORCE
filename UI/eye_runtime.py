"""Compatibility wrapper for the PySide game screen eye runtime calls."""

from UI.eye_tracking_runtime import EyeTrackingRuntime as TobiiEyeTrackingRuntime


def get_camera_index() -> int:
    return 0


class EyeTrackingRuntime(TobiiEyeTrackingRuntime):
    def start_preview(self, _camera_index=0, _on_frame=None) -> bool:
        connected, error = self.ensure_tracker()
        self.last_error = error
        return connected

    def stop_preview(self) -> None:
        return None

    def start_recording(self, _camera_index=0, _subject_id=None) -> bool:
        ok, error = self.start()
        self.last_error = error
        return ok

    def stop_recording(self, controller=None):
        features, error = self.stop(controller)
        self.last_error = error
        return features
