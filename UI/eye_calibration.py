"""Selected eye calibration flow for the configured hardware mode."""

from __future__ import annotations

from core.hardware_config import using_glasses

if using_glasses():
    from UI.eye_calibration_glasses import *  # noqa: F401,F403
else:
    from UI.eye_calibration_bar import *  # noqa: F401,F403
