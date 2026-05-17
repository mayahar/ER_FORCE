import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
from datetime import datetime
from pathlib import Path
import hashlib
import re

from core.research_repository import get_research_output_dir
from score.eye_features import has_eye_features
from styles import (
    BACKGROUND,
    NEGATIVE,
    POSITIVE,
    TEXT,
    apply_results_theme,
    score_card_html,
)


REPORTS_DIR = Path("scores_reports")


def _safe_filename_part(value):
    value = str(value or "UNKNOWN")
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_") or "UNKNOWN"


def _get_report_dir(result):
    research_context = (result or {}).get("research")

    if research_context:
        return get_research_output_dir(
            research_context,
            (result or {}).get("subject_id"),
        )

    return REPORTS_DIR


def _get_report_filename(subject_id, result):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    research_context = (result or {}).get("research")

    if research_context:
        day_number = research_context.get("day_number", "unknown_day")
        condition = _safe_filename_part(research_context.get("condition", "research"))
        return f"day_{day_number}_{condition}_{timestamp}.csv"

    return f"{_safe_filename_part(subject_id)}_{timestamp}.csv"


def _save_report_once(subject_id, csv, result=None):
    report_key = hashlib.sha256(csv.encode("utf-8-sig")).hexdigest()
    reports_dir = _get_report_dir(result)
    state_key = f"saved_report_path_{subject_id}_{reports_dir}_{report_key}"

    if state_key in st.session_state:
        return st.session_state[state_key]

    reports_dir.mkdir(parents=True, exist_ok=True)

    filename = _get_report_filename(subject_id, result)
    report_path = reports_dir / filename

    report_path.write_text(csv, encoding="utf-8-sig")

    if result is not None:
        json_path = report_path.with_suffix(".json")
        json_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    st.session_state[state_key] = str(report_path)
    return str(report_path)


def build_result_export_rows(result):
    subject_id = result.get("subject_id", "UNKNOWN")
    research_context = result.get("research") or {}
    contributions = result.get("feature_contributions", {}) or {}
    features = result.get("features", {}) or {}
    current_questionnaire = features.get("questionnaire", {}) or {}

    if not has_eye_features(features.get("eye")):
        contributions = {
            modality: feats
            for modality, feats in contributions.items()
            if modality != "eye"
        }

    export_rows = []
    graph_rows = []
    exported_features = set()

    for modality, feats in contributions.items():
        for fname, data in feats.items():
            contribution_value = data.get("weighted_contribution", 0)
            fatigue_score = data.get("fatigue_score")

            export_row = {
                "subject_id": subject_id,
                "modality": modality,
                "feature": fname,
                "baseline": data.get("baseline"),
                "current": data.get("current"),
                "fatigue_score": fatigue_score,
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
                export_row.update({
                    "study_id": research_context.get("study_id"),
                    "research_day": research_context.get("day_number"),
                    "research_condition": research_context.get("condition"),
                    "sleep_last": research_context.get("sleep_last"),
                    "sleep_previous": research_context.get("sleep_previous"),
                })

            export_rows.append(export_row)
            exported_features.add((modality, fname))

            graph_rows.append({
                "modality": modality,
                "feature": fname,
                "value": contribution_value,
            })

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
            export_row.update({
                "study_id": research_context.get("study_id"),
                "research_day": research_context.get("day_number"),
                "research_condition": research_context.get("condition"),
                "sleep_last": research_context.get("sleep_last"),
                "sleep_previous": research_context.get("sleep_previous"),
            })

        export_rows.append(export_row)

    return export_rows, graph_rows


def export_result_csv(result):
    export_rows, _ = build_result_export_rows(result)
    return pd.DataFrame(export_rows).to_csv(index=False)

def fix_hebrew(text):
    # הופך כל שורה בנפרד כדי לשמור על סדר השורות מלמעלה למטה
    lines = text.split('\n')
    fixed_lines = [line[::-1] for line in lines]
    return '\n'.join(fixed_lines)


# =========================
# SCORE COLOR MAPPING
# =========================
def get_score_color(score):

    if score <= 15:
        return "#00ff3c"  # green

    elif score <= 35:
        return "#A4FC00"  # yellow-green

    elif score <= 60:
        return "#ffd700"  # yellow

    elif score <= 80:
        return "#ea8101"  # orange

    else:
        return "#ab0000"  # red


# =========================
# MAIN RENDER
# =========================
def render(result):
    apply_results_theme()

    # =========================
    # VALIDATION
    # =========================
    st.title("תוצאות")

    if not result:
        st.error("אין נתונים להצגה")
        return

    # =========================
    # DATA
    # =========================
    subject_id = result.get("subject_id", "UNKNOWN")

    features = result.get("features", {})
    baseline = result.get("baseline", {})
    scores = result.get("scores", {})
    score = result.get("score")

    contributions = result.get("feature_contributions", {})

    # =========================
    # HEADER
    # =========================
    st.markdown(f"<h1>דוח תוצאות - {subject_id}</h1>", unsafe_allow_html=True)

    raw_paths = st.session_state.get("eye_raw_export_paths")
    if raw_paths:
        st.info(
            "קובצי עיניים גולמיים נשמרו:\n"
            f"- {raw_paths.get('json')}\n"
            f"- {raw_paths.get('csv')}"
        )

    # =========================
    # SCORE WITH GLOW
    # =========================
    if isinstance(score, (int, float)):

        color = get_score_color(score)
        st.markdown(score_card_html(score, color), unsafe_allow_html=True)

    else:
        st.error("שגיאה בחישוב ציון עייפות")

    st.divider()

    # =========================
    # FEATURE CONTRIBUTIONS TABLE
    # =========================
    export_rows, graph_rows = build_result_export_rows(result)
    df_export = pd.DataFrame(export_rows)
    df_graph = pd.DataFrame(graph_rows)

    st.divider()

    # =========================
    # CUSTOM GROUPED BAR GRAPH
    # =========================
    st.subheader("📊 פירוט המשתנים")

    if not df_graph.empty:
        fig, ax = plt.subplots(figsize=(14, 7))
        
        # הגדרת סדר הקטגוריות
        modalities = [
            modality
            for modality in ("game", "eye", "voice", "subjective")
            if modality in set(df_graph["modality"])
        ]
        modality_labels = {
            "game": "משחק",
            "eye": "עיניים",
            "voice": "קול",
            "subjective": "שאלון"
        }
        
        x_positions = []
        labels = []
        values = []
        colors = []
        
        current_x = 0
        group_boundaries = [0]

        for m in modalities:
            subset = df_graph[df_graph["modality"] == m]
            for _, row in subset.iterrows():
                x_positions.append(current_x)
                # ניקוי שמות הפיצ'רים למראה מקצועי
                clean_label = row['feature'].replace('_', '\n').title()
                labels.append(clean_label)
                values.append(row["value"])
                colors.append(NEGATIVE if row["value"] > 0 else POSITIVE)
                current_x += 1
            group_boundaries.append(current_x)

        # ציור הגרף
        ax.bar(x_positions, values, color=colors, width=0.6, zorder=3)
        ax.axhline(0, color=TEXT, linewidth=1, zorder=4)

        # --- ציר X: שמות פיצ'רים וקטגוריות ---
        ax.set_xticks([]) 
        
        for x, label in zip(x_positions, labels):
            ax.text(x, -0.1, label, ha='center', va='top', fontsize=9, color=TEXT, transform=ax.get_xaxis_transform())

        for i in range(len(modalities)):
            start = group_boundaries[i]
            end = group_boundaries[i+1]
            if start == end: continue # הגנה ממקרה של קטגוריה ריקה
            
            mid = (start + end - 1) / 2
            ax.text(mid, -0.04, fix_hebrew(modality_labels[modalities[i]]), 
                    ha='center', va='top', fontsize=12, fontweight='bold', color=TEXT, transform=ax.get_xaxis_transform())
            
            # קווי הפרדה דקים בין קבוצות
            if i > 0:
                ax.axvline(start - 0.5, color=TEXT, linewidth=0.5, alpha=0.3, zorder=1)

        # --- תוויות צד (Y) ללא חצים ---
        # הזזנו את ה-x ל- -0.12 כדי שיהיה מחוץ לציר
        ax.text(-0.12, 0.85, fix_hebrew("עלייה ברמת\nהעייפות"), transform=ax.transAxes, 
                ha='center', va='center', color=TEXT, fontsize=10,
                bbox=dict(facecolor='none', edgecolor=TEXT, alpha=0.5, pad=5))

        ax.text(-0.12, 0.15, fix_hebrew("שיפור בביצועים"), transform=ax.transAxes, 
                ha='center', va='center', color=TEXT, fontsize=10,
                bbox=dict(facecolor='none', edgecolor=TEXT, alpha=0.5, pad=5))

        # עיצוב אסתטי
        ax.set_facecolor(BACKGROUND)
        fig.patch.set_facecolor(BACKGROUND)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        ax.spines['left'].set_color(TEXT)
        ax.tick_params(axis='y', colors=TEXT, labelsize=9)

        # מתיחת הגבולות כדי שהטקסט בצד ובאמצע לא ייחתך
        plt.subplots_adjust(left=0.15, bottom=0.2)
        
        st.pyplot(fig)
    else:
        st.info("אין נתונים לגרף")

    st.divider()

    # =========================
    # ACTIONS
    # =========================
    col1, col2 = st.columns(2)

    with col1:
        if st.button("ניסיון חדש"):
            st.session_state.state["screen"] = "enter_id"
            st.session_state.result = None
            st.rerun()
    
    csv = df_export.to_csv(index=False)
    report_path = _save_report_once(subject_id, csv, result=result)
    report_filename = Path(report_path).name

    with col2:
        st.download_button(
            "יצוא תוצאות",
            data=csv,
            file_name=report_filename,
            mime="text/csv"
        )
