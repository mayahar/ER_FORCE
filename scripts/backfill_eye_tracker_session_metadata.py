from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _has_files(path: Path, patterns: tuple[str, ...]) -> bool:
    if not path.is_dir():
        return False
    return any(path.glob(pattern) for pattern in patterns)


def _read_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def infer_eye_tracker_configuration(session_root: Path) -> dict | None:
    eye_dir = session_root / "eye"
    if not eye_dir.is_dir():
        return None

    combined_recording = _read_json(eye_dir / "combined_eye_recording.json")
    combined_calibration = _read_json(eye_dir / "combined_calibration.json")
    if combined_recording.get("mode") == "combined" or combined_calibration.get("mode") == "combined":
        selected_source = (
            combined_recording.get("selected_eye_source")
            or combined_calibration.get("selected_eye_source")
        )
        bar = combined_calibration.get("bar") if isinstance(combined_calibration.get("bar"), dict) else {}
        return {
            "eye_tracker_mode": "combined",
            "using_glasses": True,
            "using_bar": True,
            "using_combined": True,
            "combined_eye_results_source": selected_source,
            "bar_head_position_enabled": bar.get("head_position_enabled"),
            "inferred_from_session_artifacts": True,
            "inference_source": "eye/combined_eye_recording.json or eye/combined_calibration.json",
        }

    glasses_dir = eye_dir / "glasses"
    bar_dir = eye_dir / "bar"
    has_glasses = _has_files(glasses_dir, ("*.json", "*.jsonl", "*.log", "*.csv"))
    has_bar = _has_files(bar_dir, ("*.json", "*.csv", "*.png"))
    if has_glasses or has_bar:
        mode = "combined" if has_glasses and has_bar else ("glasses" if has_glasses else "bar")
        return {
            "eye_tracker_mode": mode,
            "using_glasses": has_glasses,
            "using_bar": has_bar,
            "using_combined": mode == "combined",
            "combined_eye_results_source": None,
            "inferred_from_session_artifacts": True,
            "inference_source": "eye/glasses and eye/bar output directories",
        }

    legacy_bar = _has_files(
        eye_dir,
        (
            "gaze_raw_*.json",
            "gaze_raw_*.csv",
            "eye_features_*.json",
            "eye_events_*.json",
            "calibration.json",
            "calibration_fixation_map.png",
        ),
    )
    if legacy_bar:
        calibration = _read_json(eye_dir / "calibration.json")
        return {
            "eye_tracker_mode": "bar",
            "using_glasses": False,
            "using_bar": True,
            "using_combined": False,
            "combined_eye_results_source": None,
            "bar_calibration_enabled": bool(calibration) or None,
            "inferred_from_session_artifacts": True,
            "inference_source": "legacy eye directory bar outputs",
        }

    return None


def _tracker_status(
    *,
    configured: bool,
    calibration_enabled: bool | None,
    attempted: bool | None,
    passed: bool | None,
    message: str = "",
    inference_source: str,
) -> dict:
    if not configured:
        status = "not_configured"
    elif calibration_enabled is False:
        status = "skipped_by_configuration"
    elif attempted and passed:
        status = "passed"
    elif attempted:
        status = "failed"
    elif attempted is False:
        status = "not_attempted"
    else:
        status = "unknown"

    return {
        "configured": configured,
        "calibration_enabled": calibration_enabled,
        "attempted": attempted,
        "passed": passed,
        "status": status,
        "message": message,
        "inferred_from_session_artifacts": True,
        "inference_source": inference_source,
    }


def _combined_tracker_status(payload: dict, tracker: str) -> dict:
    tracker_payload = payload.get(tracker)
    tracker_payload = tracker_payload if isinstance(tracker_payload, dict) else {}
    message = str(tracker_payload.get("message") or "")
    skipped = "skipped" in message.lower()
    attempted = tracker_payload.get("attempted")
    if attempted is None:
        attempted = False if skipped else bool(tracker_payload)
    passed = tracker_payload.get("passed")
    if passed is not None:
        passed = bool(passed)
    enabled = False if skipped else True
    status = _tracker_status(
        configured=True,
        calibration_enabled=enabled,
        attempted=bool(attempted),
        passed=passed,
        message=message,
        inference_source="eye/combined_calibration.json",
    )
    if tracker == "bar" and "head_position_enabled" in tracker_payload:
        status["head_position_enabled"] = tracker_payload.get("head_position_enabled")
    return status


def _feature_calibration_status(features_path: Path) -> dict:
    features = _read_json(features_path)
    calibration = features.get("calibration") if isinstance(features.get("calibration"), dict) else {}
    if not calibration:
        return {}
    return calibration


def infer_eye_tracker_calibration_status(session_root: Path, config: dict | None = None) -> dict | None:
    eye_dir = session_root / "eye"
    if not eye_dir.is_dir():
        return None

    config = config or infer_eye_tracker_configuration(session_root) or {}
    using_glasses = bool(config.get("using_glasses"))
    using_bar = bool(config.get("using_bar"))

    combined_calibration = _read_json(eye_dir / "combined_calibration.json")
    if combined_calibration.get("mode") == "combined":
        return {
            "glasses": _combined_tracker_status(combined_calibration, "glasses"),
            "bar": _combined_tracker_status(combined_calibration, "bar"),
        }

    glasses_dir = eye_dir / "glasses"
    glasses_features = _feature_calibration_status(glasses_dir / "eye_features.json")
    glasses_configured = using_glasses or glasses_dir.is_dir()
    glasses_status = _tracker_status(
        configured=glasses_configured,
        calibration_enabled=True if glasses_configured else None,
        attempted=(
            bool(glasses_features.get("attempted"))
            if glasses_features
            else (None if glasses_configured else False)
        ),
        passed=(
            bool(glasses_features.get("passed"))
            if glasses_features and glasses_features.get("passed") is not None
            else None
        ),
        message=str(glasses_features.get("message") or "") if glasses_features else "",
        inference_source="eye/glasses/eye_features.json",
    )

    bar_dir = eye_dir / "bar"
    bar_calibration = _read_json(bar_dir / "calibration.json")
    bar_features = {}
    for candidate in bar_dir.glob("eye_features_*.json"):
        bar_features = _feature_calibration_status(candidate)
        if bar_features:
            break
    if not bar_calibration:
        bar_calibration = _read_json(eye_dir / "calibration.json")
    if not bar_features:
        for candidate in eye_dir.glob("eye_features_*.json"):
            bar_features = _feature_calibration_status(candidate)
            if bar_features:
                break

    bar_configured = using_bar or bar_dir.is_dir() or bool(bar_calibration) or bool(bar_features)
    bar_source = "eye/bar/calibration.json or legacy eye/calibration.json"
    if bar_calibration:
        bar_attempted = True
        bar_passed = bool(bar_calibration.get("passed"))
        bar_message = str(bar_calibration.get("message") or "")
    elif bar_features:
        bar_attempted = bool(bar_features.get("attempted"))
        bar_passed = (
            bool(bar_features.get("passed"))
            if bar_features.get("passed") is not None
            else None
        )
        bar_message = str(bar_features.get("message") or "")
        bar_source = "eye_features calibration metadata"
    else:
        bar_attempted = None if bar_configured else False
        bar_passed = None
        bar_message = ""

    bar_status = _tracker_status(
        configured=bar_configured,
        calibration_enabled=True if bar_configured else None,
        attempted=bar_attempted,
        passed=bar_passed,
        message=bar_message,
        inference_source=bar_source,
    )

    if not glasses_configured and not bar_configured:
        return None
    return {
        "glasses": glasses_status,
        "bar": bar_status,
    }


def iter_metadata_files(root: Path):
    yield from root.glob("sessions/*/metadata.json")
    yield from root.glob("research_results/*/participant_*/sessions/*/metadata.json")


def backfill(root: Path, dry_run: bool = False) -> tuple[int, int]:
    scanned = 0
    updated = 0
    for metadata_path in iter_metadata_files(root):
        scanned += 1
        metadata = _read_json(metadata_path)
        if not metadata:
            continue
        changed = False

        inferred = metadata.get("eye_tracker_configuration")
        if not inferred:
            inferred = infer_eye_tracker_configuration(metadata_path.parent)
            if inferred is not None:
                metadata["eye_tracker_configuration"] = inferred
                changed = True

        if not metadata.get("eye_tracker_calibration_status"):
            calibration = infer_eye_tracker_calibration_status(
                metadata_path.parent,
                inferred if isinstance(inferred, dict) else None,
            )
            if calibration is not None:
                metadata["eye_tracker_calibration_status"] = calibration
                changed = True

        if not changed:
            continue

        updated += 1
        if not dry_run:
            with metadata_path.open("w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=4)
                f.write("\n")

    return scanned, updated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    scanned, updated = backfill(REPO_ROOT, dry_run=args.dry_run)
    action = "would update" if args.dry_run else "updated"
    print(f"Scanned {scanned} metadata files; {action} {updated}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
