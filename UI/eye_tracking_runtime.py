"""Selected eye tracking runtime for the configured hardware mode."""

from __future__ import annotations

from core.hardware_config import eye_tracker_mode, using_combined, using_glasses


def _runtime_class():
    if using_combined():
        from UI.eye_tracking_runtime_combined import EyeTrackingRuntime
    elif using_glasses():
        from UI.eye_tracking_runtime_glasses import EyeTrackingRuntime
    else:
        from UI.eye_tracking_runtime_bar import EyeTrackingRuntime
    return EyeTrackingRuntime


class EyeTrackingRuntime:
    def __new__(cls, *args, **kwargs):
        runtime_cls = _runtime_class()
        return runtime_cls(*args, **kwargs)


if using_combined():
    from UI.eye_tracking_runtime_combined import SKIP_EYE_CALIBRATION
    from UI.eye_tracking_runtime_glasses import _candidate_hosts, _request
elif using_glasses():
    from UI.eye_tracking_runtime_glasses import SKIP_EYE_CALIBRATION, _candidate_hosts, _request
else:
    from UI.eye_tracking_runtime_bar import SKIP_EYE_CALIBRATION

    def _candidate_hosts(preferred_host: str | None = None) -> list[str]:
        return [preferred_host] if preferred_host else []

    def _request(*args, **kwargs):
        return None, "", f"Eye tracker mode is {eye_tracker_mode()!r}; glasses REST is disabled."
