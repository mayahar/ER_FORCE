"""Read CorrActions / FlightGear scores from session run folders."""
from __future__ import annotations

import importlib.util
import os
import re
import time
from pathlib import Path

_SCORE_RE = re.compile(r"Score:\s*(\d+)\s*/\s*100")
_EVALUATE_FN = None
_EVALUATE_LOAD_ERR: str | None = None


def _runs_root(explicit: str | None = None) -> Path | None:
    raw = (explicit or os.environ.get("SIVAKS_FG_RUNS_ROOT") or "").strip()
    if not raw:
        return None
    root = Path(raw)
    return root if root.is_dir() else None


def _launcher_script(runs_root: Path) -> Path:
    env = (
        os.environ.get("ER_FORCE_FG_SCRIPT")
        or os.environ.get("SIVAKS_LOGGING_FG_SCRIPT")
        or ""
    ).strip()
    if env:
        candidate = Path(env).expanduser()
        if candidate.is_file():
            return candidate.resolve()
    default = runs_root.parent / "logging_fg_start_ver5.py"
    return default.resolve()


def _load_evaluate_flight_score():
    global _EVALUATE_FN, _EVALUATE_LOAD_ERR
    if _EVALUATE_FN is not None:
        return _EVALUATE_FN
    if _EVALUATE_LOAD_ERR is not None:
        return None

    root = _runs_root()
    if root is None:
        _EVALUATE_LOAD_ERR = "missing runs root"
        return None

    script = _launcher_script(root)
    if not script.is_file():
        _EVALUATE_LOAD_ERR = f"missing launcher: {script}"
        return None

    try:
        spec = importlib.util.spec_from_file_location("sivaks_fg_scoring", script)
        if spec is None or spec.loader is None:
            raise ImportError("invalid module spec")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, "evaluate_flight_score", None)
        if not callable(fn):
            raise AttributeError("evaluate_flight_score missing")
        _EVALUATE_FN = fn
        return fn
    except Exception as exc:
        _EVALUATE_LOAD_ERR = str(exc)
        return None


def _score_from_report_text(text: str) -> int | None:
    match = _SCORE_RE.search(text)
    if not match:
        return None
    return max(0, min(100, int(match.group(1))))


def _session_csvs(session: Path) -> list[Path]:
    csvs = [
        path
        for path in session.glob("sivaks_logging_*.csv")
        if path.is_file() and path.stat().st_size > 0
    ]
    csvs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return csvs


def score_from_session_folder(session: Path) -> int | None:
    report = session / "final_score.txt"
    if report.is_file():
        try:
            text = report.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            text = ""
        parsed = _score_from_report_text(text)
        if parsed is not None:
            return parsed

    evaluate = _load_evaluate_flight_score()
    if evaluate is None:
        return None

    for csv_path in _session_csvs(session):
        try:
            result = evaluate(str(csv_path))
            score = int(result.get("score", 0))
            return max(0, min(100, score))
        except Exception:
            continue
    return None


def _eligible_sessions(root: Path, min_ts: float | None) -> list[Path]:
    sessions = [path for path in root.glob("session_*") if path.is_dir()]
    if min_ts is not None:
        sessions = [
            path for path in sessions
            if path.stat().st_mtime >= (min_ts - 1.0)
        ]
    sessions.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return sessions


def _min_start_ts(explicit: float | None) -> float | None:
    if explicit is not None:
        return explicit
    raw = os.environ.get("SIVAKS_FG_MIN_START_TS")
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def find_latest_flightgear_score(
    *,
    runs_root: str | None = None,
    min_ts: float | None = None,
    max_sessions: int = 10,
) -> int | None:
    root = _runs_root(runs_root)
    if root is None:
        return None

    min_start = _min_start_ts(min_ts)
    for session in _eligible_sessions(root, min_start)[:max_sessions]:
        score = score_from_session_folder(session)
        if score is not None:
            return score
    return None


def wait_for_latest_flightgear_score(
    *,
    timeout_seconds: float = 90.0,
    poll_seconds: float = 1.0,
    runs_root: str | None = None,
    min_ts: float | None = None,
) -> int | None:
    deadline = time.time() + max(0.0, timeout_seconds)
    while True:
        score = find_latest_flightgear_score(runs_root=runs_root, min_ts=min_ts)
        if score is not None:
            return score
        if time.time() >= deadline:
            return None
        time.sleep(max(0.05, poll_seconds))
