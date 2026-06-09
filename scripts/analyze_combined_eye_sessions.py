#!/usr/bin/env python3
"""Compare simultaneous Tobii bar and Tobii glasses recordings in combined sessions."""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt


START_DATE = datetime(2026, 6, 7)
MOVEMENT_METRICS = {
    "fixation_duration": "Fixation duration/min (s)",
    "fixation_count": "Fixations/min",
    "saccade_count": "Saccades/min",
}
DEVICE_LABELS = {"glasses": "Glasses", "bar": "Bar"}
DEVICE_COLORS = {"glasses": "#009E73", "bar": "#0072B2"}


@dataclass
class SessionInfo:
    subject_id: int
    session_id: str
    session_time: datetime
    path: Path
    results_json: Path


@dataclass
class RawGaze:
    time_s: np.ndarray
    valid: np.ndarray
    x: np.ndarray
    y: np.ndarray
    left_pupil: np.ndarray
    right_pupil: np.ndarray


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    main_dir = script_dir.parent
    workspace_dir = main_dir.parent
    parser = argparse.ArgumentParser(description="Analyze combined bar/glasses eye sessions.")
    parser.add_argument("--sessions-dir", type=Path, default=main_dir / "sessions")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=workspace_dir / "מחקר שלב 0.0" / "מדידה משולבת"/"combined_measurement_analysis_output",
    )
    parser.add_argument(
        "--previous-half-summary",
        type=Path,
        default=workspace_dir
        / "מחקר שלב 0.0"
        / "תנועות עיניים"
        / "quality_analysis_output"
        / "recording_quality_summary.csv",
        help="Summary CSV from the earlier eye-tracking quality analysis.",
    )
    parser.add_argument("--dpi", type=int, default=180)
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def session_name_parts(path: Path) -> tuple[int, datetime] | None:
    match = re.match(r"^(\d+)_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})$", path.name)
    if not match:
        return None
    subject_id = int(match.group(1))
    session_time = datetime.strptime(f"{match.group(2)}_{match.group(3)}", "%Y-%m-%d_%H-%M-%S")
    return subject_id, session_time


def valid_results_json(session_dir: Path) -> Path | None:
    results_dir = session_dir / "results"
    if not results_dir.is_dir():
        return None
    for path in sorted(results_dir.glob("*.json")):
        try:
            payload = read_json(path)
        except Exception:
            continue
        eye = (payload.get("features") or {}).get("eye") or {}
        invalid = payload.get("invalid_measurements") or []
        if invalid:
            continue
        if all(metric in eye and eye[metric] is not None for metric in MOVEMENT_METRICS):
            return path
    return None


def is_combined_session(session_dir: Path) -> bool:
    metadata_path = session_dir / "metadata.json"
    combined_path = session_dir / "eye" / "combined_eye_recording.json"
    if not metadata_path.is_file() or not combined_path.is_file():
        return False
    try:
        metadata = read_json(metadata_path)
        combined = read_json(combined_path)
    except Exception:
        return False
    config = metadata.get("eye_tracker_configuration") or {}
    sample_counts = combined.get("raw_sample_count") or {}
    paths = combined.get("export_paths") or {}
    return bool(
        config.get("using_combined")
        and config.get("using_glasses")
        and config.get("using_bar")
        and combined.get("mode") == "combined"
        and sample_counts.get("glasses", 0) > 0
        and sample_counts.get("bar", 0) > 0
        and paths.get("glasses")
        and paths.get("bar")
    )


def select_latest_valid_sessions(sessions_dir: Path) -> tuple[list[SessionInfo], list[dict[str, Any]]]:
    rejected: list[dict[str, Any]] = []
    latest: dict[int, SessionInfo] = {}
    for session_dir in sessions_dir.iterdir():
        if not session_dir.is_dir():
            continue
        parts = session_name_parts(session_dir)
        if parts is None:
            continue
        subject_id, session_time = parts
        if subject_id <= 100 or session_time < START_DATE:
            continue
        reasons = []
        if not is_combined_session(session_dir):
            reasons.append("not_complete_combined_session")
        results_path = valid_results_json(session_dir)
        if results_path is None:
            reasons.append("no_valid_results_json")
        if reasons:
            rejected.append(
                {
                    "subject_id": subject_id,
                    "session_id": session_dir.name,
                    "session_time": session_time.isoformat(),
                    "reason": ";".join(reasons),
                }
            )
            continue
        info = SessionInfo(subject_id, session_dir.name, session_time, session_dir, results_path)
        if subject_id not in latest or session_time > latest[subject_id].session_time:
            latest[subject_id] = info
    return sorted(latest.values(), key=lambda item: item.session_time), rejected


def finite_float(value: Any) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else np.nan
    except (TypeError, ValueError):
        return np.nan


def pair(value: Any) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return np.nan, np.nan
    return finite_float(value[0]), finite_float(value[1])


def load_glasses_raw(path: Path) -> RawGaze:
    times, x_values, y_values, left_pupil, right_pupil = [], [], [], [], []
    with path.open(encoding="utf-8") as lines:
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "gaze":
                continue
            data = event.get("data") or {}
            x, y = pair(data.get("gaze2d"))
            times.append(finite_float(event.get("timestamp")))
            x_values.append(x)
            y_values.append(y)
            left_pupil.append(finite_float((data.get("eyeleft") or {}).get("pupildiameter")))
            right_pupil.append(finite_float((data.get("eyeright") or {}).get("pupildiameter")))
    x = np.asarray(x_values, dtype=float)
    y = np.asarray(y_values, dtype=float)
    return RawGaze(
        time_s=np.asarray(times, dtype=float),
        valid=np.isfinite(x) & np.isfinite(y),
        x=x,
        y=y,
        left_pupil=np.asarray(left_pupil, dtype=float),
        right_pupil=np.asarray(right_pupil, dtype=float),
    )


def load_bar_raw(path: Path) -> RawGaze:
    frame = pd.read_csv(path)
    left_x = pd.to_numeric(frame["Left_X"], errors="coerce").to_numpy(float)
    left_y = pd.to_numeric(frame["Left_Y"], errors="coerce").to_numpy(float)
    right_x = pd.to_numeric(frame["Right_X"], errors="coerce").to_numpy(float)
    right_y = pd.to_numeric(frame["Right_Y"], errors="coerce").to_numpy(float)
    left_valid = frame["Left_Gaze_Point_Validity"].astype(str).str.lower().eq("true").to_numpy().copy()
    right_valid = frame["Right_Gaze_Point_Validity"].astype(str).str.lower().eq("true").to_numpy().copy()
    left_valid &= np.isfinite(left_x) & np.isfinite(left_y)
    right_valid &= np.isfinite(right_x) & np.isfinite(right_y)
    valid = left_valid | right_valid
    x = np.full(len(frame), np.nan)
    y = np.full(len(frame), np.nan)
    both = left_valid & right_valid
    x[both] = (left_x[both] + right_x[both]) / 2
    y[both] = (left_y[both] + right_y[both]) / 2
    x[left_valid & ~right_valid] = left_x[left_valid & ~right_valid]
    y[left_valid & ~right_valid] = left_y[left_valid & ~right_valid]
    x[right_valid & ~left_valid] = right_x[right_valid & ~left_valid]
    y[right_valid & ~left_valid] = right_y[right_valid & ~left_valid]
    return RawGaze(
        time_s=pd.to_numeric(frame["timestamp_ms"], errors="coerce").to_numpy(float) / 1000,
        valid=valid,
        x=x,
        y=y,
        left_pupil=pd.to_numeric(frame["Left_Pupil_Diameter"], errors="coerce").to_numpy(float),
        right_pupil=pd.to_numeric(frame["Right_Pupil_Diameter"], errors="coerce").to_numpy(float),
    )


def positive_deltas(raw: RawGaze) -> np.ndarray:
    deltas = np.diff(raw.time_s)
    return deltas[np.isfinite(deltas) & (deltas > 0)]


def raw_summary(raw: RawGaze) -> dict[str, float]:
    deltas = positive_deltas(raw)
    pupils = np.r_[raw.left_pupil, raw.right_pupil]
    valid_pupils = np.isfinite(pupils) & (pupils > 0)
    steps = np.hypot(np.diff(raw.x), np.diff(raw.y))
    adjacent = raw.valid[:-1] & raw.valid[1:] & np.isfinite(steps)
    return {
        "raw_sample_count": len(raw.time_s),
        "duration_s": np.nanmax(raw.time_s) - np.nanmin(raw.time_s) if len(raw.time_s) else np.nan,
        "valid_gaze_pct": 100 * np.mean(raw.valid) if len(raw.valid) else np.nan,
        "sampling_rate_hz": 1 / np.median(deltas) if len(deltas) else np.nan,
        "pupil_missing_pct": 100 * (1 - np.mean(valid_pupils)) if len(valid_pupils) else np.nan,
        "median_gaze_step": np.nanmedian(steps[adjacent]) if np.any(adjacent) else np.nan,
        "p95_gaze_step": np.nanpercentile(steps[adjacent], 95) if np.any(adjacent) else np.nan,
    }


def synchronize_distance(glasses: RawGaze, bar: RawGaze, tolerance_s: float = 0.05) -> dict[str, float]:
    g_idx = np.flatnonzero(glasses.valid & np.isfinite(glasses.time_s))
    b_idx = np.flatnonzero(bar.valid & np.isfinite(bar.time_s))
    if len(g_idx) == 0 or len(b_idx) == 0:
        return {"matched_sample_count": 0, "median_device_distance": np.nan, "p95_device_distance": np.nan}
    b_times = bar.time_s[b_idx]
    matched = []
    g_x, g_y, b_x, b_y = [], [], [], []
    for idx in g_idx:
        pos = int(np.searchsorted(b_times, glasses.time_s[idx]))
        candidates = []
        if pos < len(b_times):
            candidates.append(pos)
        if pos > 0:
            candidates.append(pos - 1)
        if not candidates:
            continue
        best = min(candidates, key=lambda item: abs(b_times[item] - glasses.time_s[idx]))
        if abs(b_times[best] - glasses.time_s[idx]) <= tolerance_s:
            b_real = b_idx[best]
            matched.append(math.hypot(glasses.x[idx] - bar.x[b_real], glasses.y[idx] - bar.y[b_real]))
            g_x.append(glasses.x[idx])
            g_y.append(glasses.y[idx])
            b_x.append(bar.x[b_real])
            b_y.append(bar.y[b_real])
    distances = np.asarray(matched, dtype=float)
    result = {
        "matched_sample_count": len(distances),
        "median_device_distance": np.nanmedian(distances) if len(distances) else np.nan,
        "p95_device_distance": np.nanpercentile(distances, 95) if len(distances) else np.nan,
    }
    if len(distances) > 2:
        result["x_correlation"] = float(np.corrcoef(g_x, b_x)[0, 1])
        result["y_correlation"] = float(np.corrcoef(g_y, b_y)[0, 1])
    else:
        result["x_correlation"] = np.nan
        result["y_correlation"] = np.nan
    return result


def feature_value(features: dict[str, Any], metric: str) -> float:
    analysis = features.get("analysis") or {}
    aliases = {
        "fixation_duration": ["fixation_duration", "fixation_duration_per_minute"],
        "fixation_count": ["fixation_count", "fixations_per_minute"],
        "saccade_count": ["saccade_count", "saccades_per_minute"],
    }
    for key in aliases[metric]:
        if key in features:
            return finite_float(features[key])
        if key in analysis:
            return finite_float(analysis[key])
    return np.nan


def analyze_sessions(sessions: list[SessionInfo]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    device_rows = []
    pair_rows = []
    session_rows = []
    for session in sessions:
        combined = read_json(session.path / "eye" / "combined_eye_recording.json")
        features = combined.get("features") or {}
        paths = combined.get("export_paths") or {}
        glasses_raw = load_glasses_raw(session.path / "eye" / "glasses" / "gazedata.jsonl")
        bar_csv = next((session.path / "eye" / "bar").glob("gaze_raw_*.csv"))
        bar_raw = load_bar_raw(bar_csv)
        sync = synchronize_distance(glasses_raw, bar_raw)
        session_rows.append(
            {
                "subject_id": session.subject_id,
                "session_id": session.session_id,
                "session_time": session.session_time.isoformat(),
                "results_json": str(session.results_json),
                **sync,
            }
        )
        for device, raw in [("glasses", glasses_raw), ("bar", bar_raw)]:
            row = {
                "subject_id": session.subject_id,
                "session_id": session.session_id,
                "session_time": session.session_time.isoformat(),
                "device": device,
                "device_label": DEVICE_LABELS[device],
                **raw_summary(raw),
            }
            for metric in MOVEMENT_METRICS:
                row[metric] = feature_value(features.get(device) or {}, metric)
            calibration = (features.get(device) or {}).get("calibration") or {}
            row["calibration_passed"] = calibration.get("passed")
            row["calibration_accuracy_px"] = (
                ((calibration.get("result") or {}).get("mean_accuracy_error_px"))
                if device == "bar"
                else np.nan
            )
            device_rows.append(row)
        paired = {
            "subject_id": session.subject_id,
            "session_id": session.session_id,
            "session_time": session.session_time.isoformat(),
            **sync,
        }
        by_device = {row["device"]: row for row in device_rows[-2:]}
        for metric in [*MOVEMENT_METRICS.keys(), "valid_gaze_pct", "sampling_rate_hz", "pupil_missing_pct"]:
            g = by_device["glasses"].get(metric)
            b = by_device["bar"].get(metric)
            paired[f"glasses_{metric}"] = g
            paired[f"bar_{metric}"] = b
            paired[f"diff_{metric}"] = g - b if pd.notna(g) and pd.notna(b) else np.nan
            paired[f"ratio_{metric}"] = g / b if pd.notna(g) and pd.notna(b) and b != 0 else np.nan
        pair_rows.append(paired)
    return pd.DataFrame(device_rows), pd.DataFrame(pair_rows), pd.DataFrame(session_rows)


def setup_style() -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "font.size": 10})


def save(fig: plt.Figure, output_dir: Path, filename: str, dpi: int) -> None:
    fig.tight_layout()
    fig.savefig(output_dir / filename, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def paired_lines(ax: plt.Axes, frame: pd.DataFrame, metric: str, title: str, ylabel: str, log: bool = False) -> None:
    pivot = frame.pivot(index="subject_id", columns="device", values=metric)
    xs = [0, 1]
    for subject, row in pivot.iterrows():
        if pd.notna(row.get("bar")) and pd.notna(row.get("glasses")):
            ax.plot(xs, [row["bar"], row["glasses"]], color="#888888", alpha=0.45, linewidth=1)
            ax.scatter(0, row["bar"], color=DEVICE_COLORS["bar"], s=32, zorder=3)
            ax.scatter(1, row["glasses"], color=DEVICE_COLORS["glasses"], s=32, zorder=3)
    ax.set_xticks(xs, ["Bar", "Glasses"])
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    if log:
        ax.set_yscale("log")


def plot_movement_metrics(device_summary: pd.DataFrame, output_dir: Path, dpi: int) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    for ax, (metric, label) in zip(axes, MOVEMENT_METRICS.items()):
        paired_lines(ax, device_summary, metric, label, label, log=True)
    fig.suptitle("Movement metrics: simultaneous bar vs glasses (log scale)")
    save(fig, output_dir, "01_movement_metrics_bar_vs_glasses.png", dpi)


def plot_ratio_metrics(paired: pd.DataFrame, output_dir: Path, dpi: int) -> None:
    fig, ax = plt.subplots(figsize=(11, 6))
    metrics = list(MOVEMENT_METRICS)
    x = np.arange(len(metrics))
    arrays = [paired[f"ratio_{metric}"].replace([np.inf, -np.inf], np.nan).dropna().to_numpy() for metric in metrics]
    boxes = ax.boxplot(arrays, positions=x, patch_artist=True)
    for patch in boxes["boxes"]:
        patch.set_facecolor("#CC79A7")
        patch.set_alpha(0.35)
    for i, metric in enumerate(metrics):
        values = paired[f"ratio_{metric}"].replace([np.inf, -np.inf], np.nan).to_numpy(float)
        ax.scatter(np.full(len(values), i) + np.linspace(-0.08, 0.08, len(values)), values, color="#333333", s=24)
    ax.axhline(1, color="#444444", linestyle=":", linewidth=1)
    ax.set_yscale("log")
    ax.set_xticks(x, [MOVEMENT_METRICS[m] for m in metrics], rotation=12)
    ax.set_title("Glasses / bar ratio for movement metrics")
    ax.set_ylabel("Ratio (log scale); 1 = equal")
    save(fig, output_dir, "02_movement_metric_ratios.png", dpi)


def plot_raw_quality(device_summary: pd.DataFrame, output_dir: Path, dpi: int) -> None:
    specs = [
        ("valid_gaze_pct", "Valid gaze samples (%)", False),
        ("sampling_rate_hz", "Sampling rate (Hz)", False),
        ("pupil_missing_pct", "Missing pupil samples (%)", False),
        ("median_gaze_step", "Median gaze step", True),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    for ax, (metric, label, log) in zip(axes.ravel(), specs):
        paired_lines(ax, device_summary, metric, label, label, log=log)
    fig.suptitle("Raw data quality: simultaneous bar vs glasses")
    save(fig, output_dir, "03_raw_quality_bar_vs_glasses.png", dpi)


def plot_device_agreement(paired: pd.DataFrame, output_dir: Path, dpi: int) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    axes[0].bar(paired["subject_id"].astype(str), paired["median_device_distance"], color="#E69F00")
    axes[0].set_title("Median device disagreement")
    axes[0].set_ylabel("Normalized gaze distance")
    axes[0].tick_params(axis="x", rotation=45)
    axes[1].bar(paired["subject_id"].astype(str), paired["p95_device_distance"], color="#D55E00")
    axes[1].set_title("95th percentile disagreement")
    axes[1].set_ylabel("Normalized gaze distance")
    axes[1].tick_params(axis="x", rotation=45)
    axes[2].scatter(paired["x_correlation"], paired["y_correlation"], color="#0072B2", s=42)
    for _, row in paired.iterrows():
        axes[2].annotate(str(int(row["subject_id"])), (row["x_correlation"], row["y_correlation"]), xytext=(4, 4), textcoords="offset points", fontsize=8)
    axes[2].set_title("Bar/glasses gaze correlation")
    axes[2].set_xlabel("X correlation")
    axes[2].set_ylabel("Y correlation")
    axes[2].axhline(0, color="#999999", linewidth=0.8)
    axes[2].axvline(0, color="#999999", linewidth=0.8)
    fig.suptitle("Approximate time-aligned agreement between devices")
    save(fig, output_dir, "04_time_aligned_device_agreement.png", dpi)


def plot_summary_heatmap(paired: pd.DataFrame, output_dir: Path, dpi: int) -> None:
    metrics = ["fixation_duration", "fixation_count", "saccade_count", "valid_gaze_pct", "pupil_missing_pct"]
    labels = ["Fix dur", "Fix count", "Sac count", "Valid gaze", "Pupil missing"]
    subjects = paired["subject_id"].astype(str).tolist()
    matrix = paired[[f"ratio_{metric}" for metric in metrics]].replace([np.inf, -np.inf], np.nan).to_numpy(float)
    log_matrix = np.log10(matrix)
    fig, ax = plt.subplots(figsize=(10, max(4, 0.35 * len(subjects))))
    cmap = plt.get_cmap("coolwarm").copy()
    cmap.set_bad("#DDDDDD")
    image = ax.imshow(np.ma.masked_invalid(log_matrix), aspect="auto", cmap=cmap, vmin=-2, vmax=2)
    ax.set_xticks(np.arange(len(labels)), labels=labels, rotation=20)
    ax.set_yticks(np.arange(len(subjects)), labels=subjects)
    ax.set_title("Glasses/bar ratio heatmap (log10)")
    ax.set_ylabel("Subject")
    colorbar = fig.colorbar(image, ax=ax)
    colorbar.set_label("log10(glasses / bar)")
    save(fig, output_dir, "05_glasses_bar_ratio_heatmap.png", dpi)


def load_previous_half_summary(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    frame = frame.loc[frame["condition"] == "half_calibration"].copy()
    if frame.empty:
        return frame
    return pd.DataFrame(
        {
            "source_group": "Previous half calibration",
            "subject_id": frame["subject"].astype(str),
            "valid_gaze_pct": pd.to_numeric(frame["valid_gaze_pct"], errors="coerce"),
            "pupil_missing_pct": pd.to_numeric(frame["pupil_missing_pct"], errors="coerce"),
            "sampling_rate_hz": pd.to_numeric(frame["sampling_rate_hz"], errors="coerce"),
            "median_gaze_step": pd.to_numeric(frame["median_gaze_step"], errors="coerce"),
            "fixation_duration": pd.to_numeric(frame["fixation_duration_per_min_s"], errors="coerce"),
            "fixation_count": pd.to_numeric(frame["fixation_count_per_min"], errors="coerce"),
            "saccade_count": pd.to_numeric(frame["saccade_count_per_min"], errors="coerce"),
        }
    )


def combined_bar_summary_for_comparison(device_summary: pd.DataFrame) -> pd.DataFrame:
    bar = device_summary.loc[device_summary["device"] == "bar"].copy()
    return pd.DataFrame(
        {
            "source_group": "Combined measurement bar",
            "subject_id": bar["subject_id"].astype(str),
            "valid_gaze_pct": pd.to_numeric(bar["valid_gaze_pct"], errors="coerce"),
            "pupil_missing_pct": pd.to_numeric(bar["pupil_missing_pct"], errors="coerce"),
            "sampling_rate_hz": pd.to_numeric(bar["sampling_rate_hz"], errors="coerce"),
            "median_gaze_step": pd.to_numeric(bar["median_gaze_step"], errors="coerce"),
            "fixation_duration": pd.to_numeric(bar["fixation_duration"], errors="coerce"),
            "fixation_count": pd.to_numeric(bar["fixation_count"], errors="coerce"),
            "saccade_count": pd.to_numeric(bar["saccade_count"], errors="coerce"),
        }
    )


def build_bar_vs_half_comparison(device_summary: pd.DataFrame, previous_half_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    previous = load_previous_half_summary(previous_half_path)
    combined = combined_bar_summary_for_comparison(device_summary)
    comparison = pd.concat([previous, combined], ignore_index=True)
    rows = []
    metrics = [
        "valid_gaze_pct",
        "pupil_missing_pct",
        "median_gaze_step",
        "fixation_duration",
        "fixation_count",
        "saccade_count",
    ]
    for metric in metrics:
        prev_values = comparison.loc[comparison["source_group"] == "Previous half calibration", metric].dropna()
        comb_values = comparison.loc[comparison["source_group"] == "Combined measurement bar", metric].dropna()
        prev_median = prev_values.median() if len(prev_values) else np.nan
        comb_median = comb_values.median() if len(comb_values) else np.nan
        rows.append(
            {
                "metric": metric,
                "previous_half_n": len(prev_values),
                "combined_bar_n": len(comb_values),
                "previous_half_median": prev_median,
                "combined_bar_median": comb_median,
                "median_difference_combined_minus_previous": comb_median - prev_median
                if pd.notna(comb_median) and pd.notna(prev_median)
                else np.nan,
                "median_ratio_combined_over_previous": comb_median / prev_median
                if pd.notna(comb_median) and pd.notna(prev_median) and prev_median != 0
                else np.nan,
                "previous_half_iqr": prev_values.quantile(0.75) - prev_values.quantile(0.25)
                if len(prev_values)
                else np.nan,
                "combined_bar_iqr": comb_values.quantile(0.75) - comb_values.quantile(0.25)
                if len(comb_values)
                else np.nan,
            }
        )
    return comparison, pd.DataFrame(rows)


def box_scatter_two_groups(ax: plt.Axes, comparison: pd.DataFrame, metric: str, ylabel: str, log: bool = False) -> None:
    groups = ["Previous half calibration", "Combined measurement bar"]
    colors = ["#56B4E9", "#D55E00"]
    arrays = [comparison.loc[comparison["source_group"] == group, metric].dropna().to_numpy(float) for group in groups]
    boxes = ax.boxplot(arrays, tick_labels=["Previous half", "Combined bar"], patch_artist=True, showfliers=False)
    for patch, color in zip(boxes["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.35)
    for i, (group, color) in enumerate(zip(groups, colors), start=1):
        values = comparison.loc[comparison["source_group"] == group, metric].dropna().to_numpy(float)
        if len(values):
            xs = np.full(len(values), i) + np.linspace(-0.07, 0.07, len(values))
            ax.scatter(xs, values, color=color, edgecolor="#333333", linewidth=0.5, s=28, zorder=3)
    ax.set_title(ylabel)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", rotation=10)
    if log:
        ax.set_yscale("log")


def plot_bar_vs_half_quality(comparison: pd.DataFrame, output_dir: Path, dpi: int) -> None:
    specs = [
        ("valid_gaze_pct", "Valid gaze samples (%)", False),
        ("pupil_missing_pct", "Missing pupil samples (%)", False),
        ("median_gaze_step", "Median gaze step", True),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    for ax, (metric, label, log) in zip(axes, specs):
        box_scatter_two_groups(ax, comparison, metric, label, log=log)
    fig.suptitle("Bar raw quality: previous half calibration vs combined measurement")
    save(fig, output_dir, "06_bar_quality_combined_vs_previous_half.png", dpi)


def plot_bar_vs_half_movement(comparison: pd.DataFrame, output_dir: Path, dpi: int) -> None:
    specs = [
        ("fixation_duration", "Fixation duration/min (s)"),
        ("fixation_count", "Fixations/min"),
        ("saccade_count", "Saccades/min"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    for ax, (metric, label) in zip(axes, specs):
        box_scatter_two_groups(ax, comparison, metric, label, log=True)
    fig.suptitle("Bar movement metrics: previous half calibration vs combined measurement")
    save(fig, output_dir, "07_bar_movement_combined_vs_previous_half.png", dpi)


def plot_bar_vs_half_median_ratios(summary: pd.DataFrame, output_dir: Path, dpi: int) -> None:
    labels = {
        "valid_gaze_pct": "Valid gaze",
        "pupil_missing_pct": "Pupil missing",
        "median_gaze_step": "Gaze step",
        "fixation_duration": "Fix dur",
        "fixation_count": "Fix count",
        "saccade_count": "Sac count",
    }
    frame = summary.copy()
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(frame))
    values = frame["median_ratio_combined_over_previous"].to_numpy(float)
    bars = ax.bar(x, values, color="#CC79A7", alpha=0.7)
    for bar, value in zip(bars, values):
        if np.isfinite(value):
            ax.text(bar.get_x() + bar.get_width() / 2, value, f"{value:.2g}x", ha="center", va="bottom", fontsize=9)
    ax.axhline(1, color="#333333", linestyle=":", linewidth=1)
    ax.set_yscale("log")
    ax.set_xticks(x, [labels.get(metric, metric) for metric in frame["metric"]], rotation=20)
    ax.set_title("Combined bar / previous half calibration median ratio")
    ax.set_ylabel("Median ratio (log scale); 1 = no change")
    save(fig, output_dir, "08_bar_combined_vs_previous_half_median_ratios.png", dpi)


def write_readme(output_dir: Path, sessions: list[SessionInfo], rejected: list[dict[str, Any]]) -> None:
    lines = [
        "# Combined eye-tracking comparison",
        "",
        "Included sessions are the latest valid combined bar+glasses session per subject from 2026-06-07 onward, with subject_id > 100.",
        "",
        f"Included subjects: {', '.join(str(s.subject_id) for s in sessions)}",
        f"Rejected candidate sessions: {len(rejected)}",
        "",
        "## Files",
        "",
        "- `selected_sessions.csv`: included sessions.",
        "- `rejected_sessions.csv`: candidate sessions excluded and why.",
        "- `device_summary.csv`: one row per subject/device with movement metrics and raw-quality metrics.",
        "- `paired_summary.csv`: one row per subject with glasses-vs-bar differences/ratios and approximate time-aligned agreement.",
        "- `bar_vs_previous_half_comparison.csv`: previous half-calibration bar recordings and combined-measurement bar recordings in one table.",
        "- `bar_vs_previous_half_summary.csv`: group medians, IQRs, differences, and ratios.",
        "",
        "## Plots",
        "",
        "- `01_movement_metrics_bar_vs_glasses.png`: paired movement metrics from the feature JSON files, shown on a log scale.",
        "- `02_movement_metric_ratios.png`: glasses/bar ratios for fixation duration, fixation count, and saccade count.",
        "- `03_raw_quality_bar_vs_glasses.png`: valid gaze rate, sampling rate, missing pupil rate, and median frame-to-frame gaze movement.",
        "- `04_time_aligned_device_agreement.png`: approximate nearest-time gaze disagreement between the two devices.",
        "- `05_glasses_bar_ratio_heatmap.png`: compact subject-by-metric ratio view; red means glasses higher than bar, blue means glasses lower.",
        "- `06_bar_quality_combined_vs_previous_half.png`: bar raw-quality comparison against the previous half-calibration recordings.",
        "- `07_bar_movement_combined_vs_previous_half.png`: bar fixation/saccade metrics compared with the previous half-calibration recordings.",
        "- `08_bar_combined_vs_previous_half_median_ratios.png`: median ratios for combined bar over previous half calibration.",
        "",
    ]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8-sig")


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    sessions, rejected = select_latest_valid_sessions(args.sessions_dir.resolve())
    if not sessions:
        raise SystemExit("No valid combined sessions found.")
    setup_style()
    device_summary, paired_summary, selected_summary = analyze_sessions(sessions)
    bar_vs_half, bar_vs_half_summary = build_bar_vs_half_comparison(device_summary, args.previous_half_summary.resolve())
    selected_summary.to_csv(output_dir / "selected_sessions.csv", index=False)
    pd.DataFrame(rejected).to_csv(output_dir / "rejected_sessions.csv", index=False)
    device_summary.to_csv(output_dir / "device_summary.csv", index=False)
    paired_summary.to_csv(output_dir / "paired_summary.csv", index=False)
    bar_vs_half.to_csv(output_dir / "bar_vs_previous_half_comparison.csv", index=False)
    bar_vs_half_summary.to_csv(output_dir / "bar_vs_previous_half_summary.csv", index=False)
    write_readme(output_dir, sessions, rejected)
    plot_movement_metrics(device_summary, output_dir, args.dpi)
    plot_ratio_metrics(paired_summary, output_dir, args.dpi)
    plot_raw_quality(device_summary, output_dir, args.dpi)
    plot_device_agreement(paired_summary, output_dir, args.dpi)
    plot_summary_heatmap(paired_summary, output_dir, args.dpi)
    if not bar_vs_half.empty:
        plot_bar_vs_half_quality(bar_vs_half, output_dir, args.dpi)
        plot_bar_vs_half_movement(bar_vs_half, output_dir, args.dpi)
        plot_bar_vs_half_median_ratios(bar_vs_half_summary, output_dir, args.dpi)
    print(f"Included {len(sessions)} sessions.")
    print(f"Wrote output to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
