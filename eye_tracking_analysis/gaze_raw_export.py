from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path

from eye_tracking_analysis.eye_tracker_recorder import EyeTrackerRecorder, GazeData

RECORDINGS_DIR_NAME = "recordings"


def gaze_recordings_dir(repo_root: Path | None = None) -> Path:
    if repo_root is not None:
        path = Path(repo_root) / "eye_tracking_analysis" / RECORDINGS_DIR_NAME
    else:
        path = Path(__file__).resolve().parent / RECORDINGS_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_subject_part(subject_id) -> str | None:
    if subject_id is None:
        return None
    text = str(subject_id).strip()
    if not text:
        return None
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")
    return safe or None


def build_gaze_raw_basename(
    subject_id=None,
    recorded_at: datetime | None = None,
) -> str:
    stamp = (recorded_at or datetime.now()).strftime("%Y%m%d_%H%M%S")
    subject_part = _safe_subject_part(subject_id)
    if subject_part:
        return f"gaze_raw_{subject_part}_{stamp}"
    return f"gaze_raw_{stamp}"


def _samples_to_rows(samples: list[GazeData]) -> list[dict]:
    return [
        {
            "timestamp": sample.timestamp,
            "left_x": sample.left_x,
            "left_y": sample.left_y,
            "right_x": sample.right_x,
            "right_y": sample.right_y,
            "left_pupil_diameter": sample.left_pupil_diameter,
            "right_pupil_diameter": sample.right_pupil_diameter,
            "validity": sample.validity,
        }
        for sample in samples
    ]


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
            "timestamp_unit": "microseconds (Tobii system_time_stamp)",
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
            "Timestamp",
            "Left_X",
            "Left_Y",
            "Right_X",
            "Right_Y",
            "Left_Pupil_Diameter",
            "Right_Pupil_Diameter",
            "Validity",
        ])
        for sample in samples:
            writer.writerow([
                sample.timestamp,
                sample.left_x,
                sample.left_y,
                sample.right_x,
                sample.right_y,
                sample.left_pupil_diameter,
                sample.right_pupil_diameter,
                sample.validity,
            ])


def export_raw_gaze_recording(
    recorder: EyeTrackerRecorder,
    *,
    output_dir: Path | None = None,
    subject_id=None,
    recorded_at: datetime | None = None,
) -> dict[str, Path]:
    samples = recorder.get_collected_data()
    if not samples:
        raise ValueError("No gaze samples in buffer to export.")

    export_dir = Path(output_dir) if output_dir else gaze_recordings_dir()
    export_dir.mkdir(parents=True, exist_ok=True)

    basename = build_gaze_raw_basename(subject_id, recorded_at)
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
