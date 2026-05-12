import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from pathlib import Path
import hashlib
import re


REPORTS_DIR = Path("scores_reports")


def _safe_filename_part(value):
    value = str(value or "UNKNOWN")
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_") or "UNKNOWN"


def _save_report_once(subject_id, csv):
    report_key = hashlib.sha256(csv.encode("utf-8-sig")).hexdigest()
    state_key = f"saved_report_path_{subject_id}_{report_key}"

    if state_key in st.session_state:
        return st.session_state[state_key]

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{_safe_filename_part(subject_id)}_{timestamp}.csv"
    report_path = REPORTS_DIR / filename

    report_path.write_text(csv, encoding="utf-8-sig")
    st.session_state[state_key] = str(report_path)
    return str(report_path)

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

    # =========================
    # THEME (unchanged)
    # =========================
    st.markdown("""
    <style>
    .stApp {
        background-color: #001122;
        color: white;
        direction: rtl;
        font-family: 'Courier New', monospace;
    }

    h1, h2, h3 {
        color: #66aaff;
        text-shadow: 0 0 10px #66aaff;
        text-align: center;
    }

    .block-box {
        background-color: #002244;
        border: 1px solid #004466;
        padding: 12px;
        border-radius: 8px;
        margin-bottom: 10px;
    }

    .metric-box {
        background-color: #001a33;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        margin-bottom: 20px;
    }

    .stButton > button {
        background-color: #0066cc;
        color: white;
        border-radius: 6px;
        font-weight: bold;
    }

    .stButton > button:hover {
        background-color: #004499;
    }

    .stDownloadButton > button {
        background-color: #0066cc;
        color: white;
        border-radius: 6px;
        font-weight: bold;
    }
    
    .stDownloadButton > button:hover {
        background-color: #004499;
    }           
    
    </style>
    """, unsafe_allow_html=True)

    

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

    # =========================
    # SCORE WITH GLOW
    # =========================
    if isinstance(score, (int, float)):

        color = get_score_color(score)

        st.markdown(f"""
        <div style="
            text-align:center;
            padding:25px;
            border-radius:20px;
            box-shadow: 0 0 30px {color};
            border: 2px solid {color};
            margin-bottom:20px;
        ">
            <h2>רמת עייפות</h2>
            <h1 style="color:{color}; font-size:60px;">
                {score:.2f}
            </h1>
        </div>
        """, unsafe_allow_html=True)

    else:
        st.error("שגיאה בחישוב ציון עייפות")

    st.divider()

    # =========================
    # FEATURE CONTRIBUTIONS TABLE
    # =========================
    export_rows = []
    graph_rows = []

    for modality, feats in contributions.items():

        for fname, data in feats.items():

            contribution_value = data.get(
                "weighted_contribution",
                0
            )

            export_rows.append({

                # -------------------------
                # identifiers
                # -------------------------

                "modality": modality,
                "feature": fname,

                # -------------------------
                # values
                # -------------------------

                "baseline": data.get("baseline"),
                "current": data.get("current"),

                # -------------------------
                # scoring internals
                # -------------------------

                "fatigue_score": data.get(
                    "fatigue_score"
                ),

                "relative_change": data.get(
                    "relative_change"
                ),

                "normalized_effect": data.get(
                    "normalized_effect"
                ),

                "raw_sigmoid": data.get(
                    "raw_sigmoid"
                ),

                # -------------------------
                # config
                # -------------------------

                "weight": data.get("weight"),

                "direction": data.get(
                    "direction"
                ),

                "expected_change": data.get(
                    "expected_change"
                ),

                # -------------------------
                # final contribution
                # -------------------------

                "contribution": contribution_value,

                "better_than_baseline": data.get(
                    "better_than_baseline"
                )
            })

            graph_rows.append({

                "modality": modality,

                "feature": fname,

                "value": contribution_value
            })
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
        modalities = ["game", "eye", "voice"]
        modality_labels = {"game": "משחק", "eye": "עיניים", "voice": "קול"}
        
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
                colors.append("#ef4444" if row["value"] > 0 else "#84cc16")
                current_x += 1
            group_boundaries.append(current_x)

        # ציור הגרף
        ax.bar(x_positions, values, color=colors, width=0.6, zorder=3)
        ax.axhline(0, color="white", linewidth=1, zorder=4)

        # --- ציר X: שמות פיצ'רים וקטגוריות ---
        ax.set_xticks([]) 
        
        for x, label in zip(x_positions, labels):
            ax.text(x, -0.1, label, ha='center', va='top', fontsize=9, color="white", transform=ax.get_xaxis_transform())

        for i in range(len(modalities)):
            start = group_boundaries[i]
            end = group_boundaries[i+1]
            if start == end: continue # הגנה ממקרה של קטגוריה ריקה
            
            mid = (start + end - 1) / 2
            ax.text(mid, -0.04, fix_hebrew(modality_labels[modalities[i]]), 
                    ha='center', va='top', fontsize=12, fontweight='bold', color="white", transform=ax.get_xaxis_transform())
            
            # קווי הפרדה דקים בין קבוצות
            if i > 0:
                ax.axvline(start - 0.5, color="white", linewidth=0.5, alpha=0.3, zorder=1)

        # --- תוויות צד (Y) ללא חצים ---
        # הזזנו את ה-x ל- -0.12 כדי שיהיה מחוץ לציר
        ax.text(-0.12, 0.85, fix_hebrew("עלייה ברמת\nהעייפות"), transform=ax.transAxes, 
                ha='center', va='center', color="white", fontsize=10, 
                bbox=dict(facecolor='none', edgecolor='white', alpha=0.5, pad=5))

        ax.text(-0.12, 0.15, fix_hebrew("שיפור בביצועים"), transform=ax.transAxes, 
                ha='center', va='center', color="white", fontsize=10, 
                bbox=dict(facecolor='none', edgecolor='white', alpha=0.5, pad=5))

        # עיצוב אסתטי
        ax.set_facecolor("#001122")
        fig.patch.set_facecolor("#001122")
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        ax.spines['left'].set_color('white')
        ax.tick_params(axis='y', colors="white", labelsize=9)

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
    report_path = _save_report_once(subject_id, csv)
    report_filename = Path(report_path).name

    with col2:
        st.download_button(
            "יצוא תוצאות",
            data=csv,
            file_name=report_filename,
            mime="text/csv"
        )
