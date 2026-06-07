"""Single switch for the eye-tracker hardware used by the app."""

from __future__ import annotations

import os

# Change this value to switch the application between the two recording flows.
# Supported values:
#   "glasses" - Tobii Pro Glasses 3 eye + glasses audio flow
#   "bar"     - screen-mounted Tobii bar eye flow + local microphone audio
#   "combined"- Tobii Pro Glasses 3 + screen-mounted Tobii bar
EYE_TRACKER_MODE = "combined"

# In combined mode both eye trackers are recorded, but this source is used for
# the final fatigue score. Change to "bar" if the scoring source should switch.
COMBINED_EYE_RESULTS_SOURCE = os.environ.get(
    "ER_FORCE_COMBINED_EYE_RESULTS_SOURCE",
    "glasses",
)


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
        "combined": "combined",
        "combo": "combined",
        "glasses_bar": "combined",
        "bar_glasses": "combined",
        "glasses_and_bar": "combined",
        "glasses_plus_bar": "combined",
    }
    if mode not in aliases:
        supported = ", ".join(sorted(set(aliases.values())))
        raise ValueError(f"Unsupported EYE_TRACKER_MODE {mode!r}. Use one of: {supported}.")
    return aliases[mode]


def using_glasses() -> bool:
    return eye_tracker_mode() in {"glasses", "combined"}


def using_bar() -> bool:
    return eye_tracker_mode() in {"bar", "combined"}


def using_combined() -> bool:
    return eye_tracker_mode() == "combined"


def combined_eye_results_source() -> str:
    source = str(COMBINED_EYE_RESULTS_SOURCE).strip().lower().replace("-", "_")
    aliases = {
        "glasses": "glasses",
        "glass": "glasses",
        "tobii_glasses": "glasses",
        "bar": "bar",
        "screen_bar": "bar",
        "tobii_bar": "bar",
    }
    return aliases.get(source, "glasses")
