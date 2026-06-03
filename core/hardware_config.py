"""Single switch for the eye-tracker hardware used by the app."""

from __future__ import annotations

import os

# Change this value to switch the application between the two recording flows.
# Supported values:
#   "glasses" - Tobii Pro Glasses 3 eye + glasses audio flow
#   "bar"     - screen-mounted Tobii bar eye flow + local microphone audio
EYE_TRACKER_MODE = "bar"


def eye_tracker_mode() -> str:
    mode = os.environ.get("ER_FORCE_EYE_TRACKER_MODE", EYE_TRACKER_MODE)
    mode = str(mode).strip().lower().replace("-", "_")
    aliases = {
        "glasses": "glasses",
        "glass": "glasses",
        "tobii_glasses": "glasses",
        "tobii_pro_glasses_3": "glasses",
        "bar": "bar",
        "screen_bar": "bar",
        "tobii_bar": "bar",
        "tobii_pro": "bar",
    }
    if mode not in aliases:
        supported = ", ".join(sorted(set(aliases.values())))
        raise ValueError(f"Unsupported EYE_TRACKER_MODE {mode!r}. Use one of: {supported}.")
    return aliases[mode]


def using_glasses() -> bool:
    return eye_tracker_mode() == "glasses"


def using_bar() -> bool:
    return eye_tracker_mode() == "bar"
