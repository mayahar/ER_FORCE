"""Single switch for the eye-tracker hardware used by the app."""

from __future__ import annotations

import json
import os
from pathlib import Path

# Change this value to switch the application between the two recording flows.
# Supported values:
#   "glasses" - Tobii Pro Glasses 3 eye + glasses audio flow
#   "bar"     - screen-mounted Tobii bar eye flow + local microphone audio
#   "combined"- Tobii Pro Glasses 3 + screen-mounted Tobii bar
EYE_TRACKER_MODE = "combined"
BAR_CALIBRATION_MODE = "without_head"
GLASSES_CALIBRATION_ENABLED = True
GLASSES_HOST = ""

CONFIG_PATH = Path(__file__).with_name("hardware_config.json")

# In combined mode both eye trackers are recorded, but this source is used for
# the final fatigue score. Change to "bar" if the scoring source should switch.
COMBINED_EYE_RESULTS_SOURCE = os.environ.get(
    "ER_FORCE_COMBINED_EYE_RESULTS_SOURCE",
    "glasses",
)


def load_hardware_config() -> dict:
    config = {
        "eye_tracker_mode": EYE_TRACKER_MODE,
        "combined_eye_results_source": COMBINED_EYE_RESULTS_SOURCE,
        "bar_calibration_mode": BAR_CALIBRATION_MODE,
        "glasses_calibration_enabled": GLASSES_CALIBRATION_ENABLED,
        "glasses_host": GLASSES_HOST,
    }
    if CONFIG_PATH.is_file():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                config.update(data)
        except Exception:
            pass
    return config


def save_hardware_config(config: dict) -> None:
    current = load_hardware_config()
    current.update(config)
    current["eye_tracker_mode"] = _normalize_eye_tracker_mode(current["eye_tracker_mode"])
    current["combined_eye_results_source"] = _normalize_combined_eye_results_source(
        current.get("combined_eye_results_source", "glasses")
    )
    current["bar_calibration_mode"] = _normalize_bar_calibration_mode(
        current.get("bar_calibration_mode", BAR_CALIBRATION_MODE)
    )
    current["glasses_calibration_enabled"] = bool(
        current.get("glasses_calibration_enabled", GLASSES_CALIBRATION_ENABLED)
    )
    current["glasses_host"] = str(current.get("glasses_host") or "").strip()
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(current, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _normalize_eye_tracker_mode(mode: str) -> str:
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


def eye_tracker_mode() -> str:
    mode = os.environ.get("ER_FORCE_EYE_TRACKER_MODE", load_hardware_config()["eye_tracker_mode"])
    return _normalize_eye_tracker_mode(mode)


def _normalize_bar_calibration_mode(mode: str) -> str:
    mode = str(mode).strip().lower().replace("-", "_")
    aliases = {
        "with_head": "with_head",
        "head": "with_head",
        "head_position": "with_head",
        "without_head": "without_head",
        "no_head": "without_head",
        "dots_only": "without_head",
        "none": "none",
        "no_calibration": "none",
        "skip": "none",
    }
    if mode not in aliases:
        raise ValueError("Unsupported bar calibration mode.")
    return aliases[mode]


def bar_calibration_mode() -> str:
    mode = os.environ.get(
        "ER_FORCE_BAR_CALIBRATION_MODE",
        load_hardware_config()["bar_calibration_mode"],
    )
    return _normalize_bar_calibration_mode(mode)


def bar_head_position_enabled() -> bool:
    return bar_calibration_mode() == "with_head"


def calibrate_bar() -> bool:
    return bar_calibration_mode() != "none"


def calibrate_glasses() -> bool:
    env_value = os.environ.get("ER_FORCE_GLASSES_CALIBRATION_ENABLED")
    if env_value is not None:
        return env_value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(load_hardware_config()["glasses_calibration_enabled"])


def glasses_host() -> str:
    return os.environ.get(
        "TOBII_GLASSES_HOST",
        os.environ.get(
            "ER_FORCE_GLASSES_HOST",
            load_hardware_config().get("glasses_host", GLASSES_HOST),
        ),
    ).strip()


def skip_eye_calibration() -> bool:
    mode = eye_tracker_mode()
    if mode == "bar":
        return not calibrate_bar()
    if mode == "glasses":
        return not calibrate_glasses()
    return not (calibrate_glasses() or calibrate_bar())


def using_glasses() -> bool:
    return eye_tracker_mode() in {"glasses", "combined"}


def using_bar() -> bool:
    return eye_tracker_mode() in {"bar", "combined"}


def using_combined() -> bool:
    return eye_tracker_mode() == "combined"


def _normalize_combined_eye_results_source(source: str) -> str:
    source = str(source).strip().lower().replace("-", "_")
    aliases = {
        "glasses": "glasses",
        "glass": "glasses",
        "tobii_glasses": "glasses",
        "bar": "bar",
        "screen_bar": "bar",
        "tobii_bar": "bar",
    }
    return aliases.get(source, "glasses")


def combined_eye_results_source() -> str:
    source = os.environ.get(
        "ER_FORCE_COMBINED_EYE_RESULTS_SOURCE",
        load_hardware_config()["combined_eye_results_source"],
    )
    return _normalize_combined_eye_results_source(source)


def eye_tracker_configuration_snapshot() -> dict:
    """Return the effective eye-tracker configuration for session metadata."""
    env_overrides = {
        name: os.environ[name]
        for name in (
            "ER_FORCE_EYE_TRACKER_MODE",
            "ER_FORCE_BAR_CALIBRATION_MODE",
            "ER_FORCE_GLASSES_CALIBRATION_ENABLED",
            "ER_FORCE_GLASSES_HOST",
            "TOBII_GLASSES_HOST",
            "ER_FORCE_COMBINED_EYE_RESULTS_SOURCE",
        )
        if name in os.environ
    }
    mode = eye_tracker_mode()
    bar_mode = bar_calibration_mode()
    glasses_host_value = glasses_host()

    return {
        "eye_tracker_mode": mode,
        "using_glasses": mode in {"glasses", "combined"},
        "using_bar": mode in {"bar", "combined"},
        "using_combined": mode == "combined",
        "combined_eye_results_source": combined_eye_results_source(),
        "bar_calibration_mode": bar_mode,
        "bar_calibration_enabled": bar_mode != "none",
        "bar_head_position_enabled": bar_mode == "with_head",
        "glasses_calibration_enabled": calibrate_glasses(),
        "glasses_host": glasses_host_value,
        "glasses_host_configured": bool(glasses_host_value),
        "config_file": str(CONFIG_PATH),
        "environment_overrides": env_overrides,
    }
