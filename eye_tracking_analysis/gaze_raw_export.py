from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from eye_tracking_analysis.eye_tracker_recorder import EyeTrackerRecorder, GazeData

RECORDINGS_DIR_NAME = "recordings"


def gaze_recordings_dir(repo_root: Path | None = None) -> Path:
    if repo_root is not None:
        path = Path(repo_root) / "eye_tracking_analysis" / RECORDINGS_DIR_NAME
    else:
        path = Path(__file__).resolve().parent / RECORDINGS_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_part(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")
    return safe or None


def build_gaze_raw_basename(
    subject_id=None,
    recorded_at: datetime | None = None,
    session_id: str | None = None,
) -> str:
    if session_id:
        safe_session = _safe_part(session_id)
        if safe_session:
            return f"gaze_raw_{safe_session}"
    stamp = (recorded_at or datetime.now()).strftime("%Y%m%d_%H%M%S")
    subject_part = _safe_part(subject_id)
    if subject_part:
        return f"gaze_raw_{subject_part}_{stamp}"
    return f"gaze_raw_{stamp}"


def build_eye_features_basename(
    subject_id=None,
    recorded_at: datetime | None = None,
    session_id: str | None = None,
) -> str:
    raw = build_gaze_raw_basename(subject_id, recorded_at, session_id)
    return raw.replace("gaze_raw_", "eye_features_", 1)


def build_eye_events_basename(
    subject_id=None,
    recorded_at: datetime | None = None,
    session_id: str | None = None,
) -> str:
    raw = build_gaze_raw_basename(subject_id, recorded_at, session_id)
    return raw.replace("gaze_raw_", "eye_events_", 1)


def timestamps_relative_ms(samples: list[GazeData]) -> np.ndarray:
    """Convert Tobii timestamps to milliseconds relative to the first sample."""
    if not samples:
        return np.array([], dtype=float)

    timestamps = np.array([sample.timestamp for sample in samples], dtype=float)
    if timestamps.size == 0:
        return timestamps

    # Tobii system_time_stamp is microseconds since epoch.
    if np.nanmax(timestamps) > 1e5:
        timestamps = timestamps / 1000.0

    timestamps = timestamps - timestamps[0]
    return timestamps


def _samples_to_rows(samples: list[GazeData]) -> list[dict]:
    timestamps_ms = timestamps_relative_ms(samples)
    rows = []
    for index, sample in enumerate(samples):
        rows.append(
            {
                "timestamp_ms": float(timestamps_ms[index]),
                "timestamp_raw": sample.timestamp,
                "left_x": sample.left_x,
                "left_y": sample.left_y,
                "right_x": sample.right_x,
                "right_y": sample.right_y,
                "left_pupil_diameter": sample.left_pupil_diameter,
                "right_pupil_diameter": sample.right_pupil_diameter,
                "validity": sample.validity,
            }
        )
    return rows


def write_raw_gaze_json(
    samples: list[GazeData],
    json_path: Path,
    recorder: EyeTrackerRecorder,
) -> None:
    payload = {
        "metadata": {
            "start_time": (
                recorder.start_time.isoformat() if recorder.start_time else None
            ),
            "end_time": (
                recorder.end_time.isoformat() if recorder.end_time else None
            ),
            "total_samples": len(samples),
            "eyetracker_model": (
                recorder.eyetracker.model if recorder.eyetracker else None
            ),
            "eyetracker_serial": (
                recorder.eyetracker.serial_number if recorder.eyetracker else None
            ),
            "timestamp_ms_unit": "milliseconds since first gaze sample",
            "timestamp_raw_unit": "Tobii system_time_stamp (microseconds)",
        },
        "gaze_data": _samples_to_rows(samples),
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_raw_gaze_csv(samples: list[GazeData], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "timestamp_ms",
            "timestamp_raw",
            "Left_X",
            "Left_Y",
            "Right_X",
            "Right_Y",
            "Left_Pupil_Diameter",
            "Right_Pupil_Diameter",
            "Validity",
        ])
        for row in _samples_to_rows(samples):
            writer.writerow([
                row["timestamp_ms"],
                row["timestamp_raw"],
                row["left_x"],
                row["left_y"],
                row["right_x"],
                row["right_y"],
                row["left_pupil_diameter"],
                row["right_pupil_diameter"],
                row["validity"],
            ])


def _seconds_to_ms(value: float) -> float:
    return float(value) * 1000.0


def _fixation_to_dict(fixation) -> dict[str, Any]:
    return {
        "start_time_ms": _seconds_to_ms(fixation.start_time),
        "end_time_ms": _seconds_to_ms(fixation.end_time),
        "duration_ms": _seconds_to_ms(fixation.duration),
        "x": float(fixation.x),
        "y": float(fixation.y),
        "amplitude": fixation.amplitude,
    }


def _saccade_to_dict(saccade) -> dict[str, Any]:
    return {
        "start_time_ms": _seconds_to_ms(saccade.start_time),
        "end_time_ms": _seconds_to_ms(saccade.end_time),
        "duration_ms": _seconds_to_ms(saccade.duration),
        "amplitude": float(saccade.amplitude),
        "velocity": float(saccade.velocity),
        "start_x": float(saccade.start_x),
        "start_y": float(saccade.start_y),
        "end_x": float(saccade.end_x),
        "end_y": float(saccade.end_y),
    }


def _metrics_to_dict(metrics) -> dict[str, Any]:
    return {
        "total_duration_s": float(metrics.total_duration),
        "num_fixations": int(metrics.num_fixations),
        "num_saccades": int(metrics.num_saccades),
        "fixations_per_minute": float(metrics.fixations_per_minute),
        "saccades_per_minute": float(metrics.saccades_per_minute),
        "mean_fixation_duration_s": float(metrics.mean_fixation_duration),
        "median_fixation_duration_s": float(metrics.median_fixation_duration),
        "total_fixation_duration_s": float(metrics.total_fixation_duration),
        "fixation_duration_per_minute_s": float(metrics.fixation_duration_per_minute),
        "mean_saccade_duration_s": float(metrics.mean_saccade_duration),
        "mean_saccade_amplitude": float(metrics.mean_saccade_amplitude),
        "mean_saccade_velocity": float(metrics.mean_saccade_velocity),
        "blink_rate": float(metrics.blink_rate),
    }


def write_eye_features_json(features: dict[str, Any] | None, json_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = features or {}
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_eye_features_csv(features: dict[str, Any] | None, csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    payload = features or {}
    scoring_keys = ("fixation_duration", "fixation_count", "saccade_count")
    row = {key: payload.get(key) for key in scoring_keys}
    analysis = payload.get("analysis") or {}
    for key, value in analysis.items():
        row[f"analysis_{key}"] = value

    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)


def write_eye_events_json(
    fixations,
    saccades,
    metrics,
    json_path: Path,
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {
            "time_unit": "milliseconds since first gaze sample",
        },
        "fixations": [_fixation_to_dict(item) for item in (fixations or [])],
        "saccades": [_saccade_to_dict(item) for item in (saccades or [])],
        "metrics": _metrics_to_dict(metrics) if metrics is not None else None,
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def export_raw_gaze_recording(
    recorder: EyeTrackerRecorder,
    *,
    output_dir: Path | None = None,
    subject_id=None,
    session_id: str | None = None,
    recorded_at: datetime | None = None,
) -> dict[str, Path]:
    samples = recorder.get_collected_data()
    if not samples:
        raise ValueError("No gaze samples in buffer to export.")

    export_dir = Path(output_dir) if output_dir else gaze_recordings_dir()
    export_dir.mkdir(parents=True, exist_ok=True)

    basename = build_gaze_raw_basename(subject_id, recorded_at, session_id)
    json_path = (export_dir / f"{basename}.json").resolve()
    csv_path = (export_dir / f"{basename}.csv").resolve()

    write_raw_gaze_json(samples, json_path, recorder)
    write_raw_gaze_csv(samples, csv_path)

    return {
        "json": json_path,
        "csv": csv_path,
        "sample_count": len(samples),
        "directory": export_dir.resolve(),
    }


def export_eye_session_recording(
    recorder: EyeTrackerRecorder,
    *,
    output_dir: Path | None = None,
    subject_id=None,
    session_id: str | None = None,
    recorded_at: datetime | None = None,
    features: dict[str, Any] | None = None,
    fixations=None,
    saccades=None,
    metrics=None,
) -> dict[str, Any]:
    """Write raw gaze (ms) and derived eye features/events into the session eye folder."""
    raw_paths = export_raw_gaze_recording(
        recorder,
        output_dir=output_dir,
        subject_id=subject_id,
        session_id=session_id,
        recorded_at=recorded_at,
    )

    export_dir = Path(raw_paths["directory"])
    features_basename = build_eye_features_basename(subject_id, recorded_at, session_id)
    events_basename = build_eye_events_basename(subject_id, recorded_at, session_id)

    features_json = (export_dir / f"{features_basename}.json").resolve()
    features_csv = (export_dir / f"{features_basename}.csv").resolve()
    events_json = (export_dir / f"{events_basename}.json").resolve()

    write_eye_features_json(features, features_json)
    write_eye_features_csv(features, features_csv)
    write_eye_events_json(fixations, saccades, metrics, events_json)

    return {
        **raw_paths,
        "features_json": features_json,
        "features_csv": features_csv,
        "events_json": events_json,
    }
