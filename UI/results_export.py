import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from core.research_repository import get_research_output_dir


REPORTS_DIR = Path("scores_reports")
_SAVED_REPORTS = set()


def safe_filename_part(value):
    value = str(value or "UNKNOWN")
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_") or "UNKNOWN"


def get_report_dir(result, controller=None):
    if controller and getattr(controller, "session", None):
        return controller.session.results_dir

    research_context = (result or {}).get("research")
    if research_context:
        return get_research_output_dir(research_context, (result or {}).get("subject_id"))

    return REPORTS_DIR


def get_report_filename(subject_id, result):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    research_context = (result or {}).get("research")

    if research_context:
        day_number = research_context.get("day_number", "unknown_day")
        condition = safe_filename_part(research_context.get("condition", "research"))
        return f"day_{day_number}_{condition}_{timestamp}.csv"

    return f"{safe_filename_part(subject_id)}_{timestamp}.csv"


def save_report_once(subject_id, csv_text, result=None, controller=None):
    reports_dir = get_report_dir(result, controller)
    report_key = hashlib.sha256(csv_text.encode("utf-8-sig")).hexdigest()
    state_key = f"{subject_id}:{reports_dir}:{report_key}"

    if state_key in _SAVED_REPORTS:
        return None

    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / get_report_filename(subject_id, result)
    report_path.write_text(csv_text, encoding="utf-8-sig")

    if result is not None:
        report_path.with_suffix(".json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    _SAVED_REPORTS.add(state_key)
    return str(report_path)


def build_result_export_rows(result):
    subject_id = result.get("subject_id", "UNKNOWN")
    research_context = result.get("research") or {}
    contributions = result.get("feature_contributions", {})
    current_questionnaire = (result.get("features", {}) or {}).get("questionnaire", {}) or {}

    export_rows = []
    graph_rows = []
    exported_features = set()

    for modality, feats in contributions.items():
        for fname, data in feats.items():
            contribution_value = data.get("weighted_contribution", 0)
            export_row = {
                "subject_id": subject_id,
                "modality": modality,
                "feature": fname,
                "baseline": data.get("baseline"),
                "current": data.get("current"),
                "fatigue_score": data.get("fatigue_score"),
                "relative_change": data.get("relative_change"),
                "normalized_effect": data.get("normalized_effect"),
                "raw_sigmoid": data.get("raw_sigmoid"),
                "weight": data.get("weight"),
                "direction": data.get("direction"),
                "expected_change": data.get("expected_change"),
                "contribution": contribution_value,
                "weighted_contribution": contribution_value,
                "better_than_baseline": data.get("better_than_baseline"),
            }

            if research_context:
                export_row.update(
                    {
                        "study_id": research_context.get("study_id"),
                        "research_day": research_context.get("day_number"),
                        "research_condition": research_context.get("condition"),
                        "sleep_last": research_context.get("sleep_last"),
                        "sleep_previous": research_context.get("sleep_previous"),
                    }
                )

            export_rows.append(export_row)
            exported_features.add((modality, fname))
            graph_rows.append(
                {
                    "modality": modality,
                    "feature": fname,
                    "value": contribution_value,
                }
            )

    for fname, current_value in current_questionnaire.items():
        if ("subjective", fname) in exported_features:
            continue

        export_row = {
            "subject_id": subject_id,
            "modality": "subjective",
            "feature": fname,
            "baseline": None,
            "current": current_value,
            "fatigue_score": None,
            "relative_change": None,
            "normalized_effect": None,
            "raw_sigmoid": None,
            "weight": None,
            "direction": None,
            "expected_change": None,
            "contribution": None,
            "weighted_contribution": None,
            "better_than_baseline": None,
        }

        if research_context:
            export_row.update(
                {
                    "study_id": research_context.get("study_id"),
                    "research_day": research_context.get("day_number"),
                    "research_condition": research_context.get("condition"),
                    "sleep_last": research_context.get("sleep_last"),
                    "sleep_previous": research_context.get("sleep_previous"),
                }
            )

        export_rows.append(export_row)

    return export_rows, graph_rows


def export_result_csv(result):
    export_rows, _ = build_result_export_rows(result)
    return pd.DataFrame(export_rows).to_csv(index=False)

