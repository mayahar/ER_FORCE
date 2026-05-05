import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt


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
        border: 2px solid #0066cc;
        padding: 15px;
        border-radius: 10px;
        text-align: center;
        box-shadow: 0 0 10px #0066cc;
        margin-bottom: 20px;
    }

    .section-title {
        color: #66aaff;
        font-size: 18px;
        margin-bottom: 10px;
        text-shadow: 0 0 6px #66aaff;
    }

    .stButton > button {
        background-color: #0066cc;
        color: white;
        border: none;
        border-radius: 5px;
        font-weight: bold;
        box-shadow: 0 0 10px #0066cc;
    }

    .stButton > button:hover {
        background-color: #004499;
        box-shadow: 0 0 20px #0066cc;
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
    # PARSE DATA
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
    st.markdown(f"<h1>דוח תוצאות - ID: {subject_id}</h1>", unsafe_allow_html=True)

    # =========================
    # SCORE DISPLAY
    # =========================
    if isinstance(score, (int, float)):
        st.markdown('<div class="metric-box">', unsafe_allow_html=True)
        st.markdown("<h2>רמת עייפות</h2>", unsafe_allow_html=True)
        st.markdown(f"<h1>{score:.2f}</h1>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.error("שגיאה בחישוב ציון עייפות")

    st.divider()

    # =========================
    # FEATURE VIEW
    # =========================
    def pretty_block(title, data):
        st.markdown('<div class="block-box">', unsafe_allow_html=True)
        st.markdown(f"<div class='section-title'>{title}</div>", unsafe_allow_html=True)
        st.json(data)
        st.markdown("</div>", unsafe_allow_html=True)


    # =========================
    # CONTRIBUTION GRAPH
    # =========================
    st.subheader("📉 תרומת פיצ'רים לציון העייפות")

    rows = []

    for modality, feats in contributions.items():
        for fname, data in feats.items():

            rows.append({
                "feature": f"{modality}.{fname}",
                "contribution": data["value"],
                "weight": data["weight"],
                "raw_score": data["raw_score"],
                "direction": data["direction"]
            })

    df = pd.DataFrame(rows)

    if not df.empty:

        df = df.sort_values("contribution")

        fig, ax = plt.subplots()

        colors = ["red" if x > 0 else "green" for x in df["contribution"]]

        ax.barh(df["feature"], df["contribution"], color=colors)

        ax.axvline(0, color="white", linewidth=1)

        ax.set_facecolor("#001122")
        fig.patch.set_facecolor("#001122")

        ax.tick_params(colors="white")

        ax.set_title("Contribution (weight × feature score)", color="white")

        st.pyplot(fig)

        st.dataframe(df)

    else:
        st.info("אין נתוני contributions להצגה")

    st.divider()


    st.subheader("📊 פרטי מדידות")

    col1, col2, col3 = st.columns(3)

    with col1:
        pretty_block("👁️ עכשיו", features.get("eye", {}))
        pretty_block("👁️ בסיס", baseline.get("eye", {}))

    with col2:
        pretty_block("🎮 עכשיו", features.get("game", {}))
        pretty_block("🎮 בסיס", baseline.get("game", {}))

    with col3:
        pretty_block("🎙️ עכשיו", features.get("voice", {}))
        pretty_block("🎙️ בסיס", baseline.get("voice", {}))

    st.divider()

    # =========================
    # MODALITY BREAKDOWN
    # =========================
    if scores:
        st.subheader("📈 פירוק לפי מודל")

        st.markdown('<div class="block-box">', unsafe_allow_html=True)
        st.json(scores)
        st.markdown("</div>", unsafe_allow_html=True)

    # =========================
    # FEATURE TABLE PER MODALITY
    # =========================
    st.subheader("🔬 פירוט מלא לפי פיצ'ר")

    for modality, feats in contributions.items():

        st.markdown(f"### {modality.upper()}")

        table = []

        for fname, data in feats.items():
            table.append({
                "feature": fname,
                "contribution": data["value"],
                "weight": data["weight"],
                "score": data["raw_score"],
                "direction": data["direction"]
            })

        st.dataframe(pd.DataFrame(table))

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

    with col2:
        st.download_button(
            "יצוא תוצאות",
            data=str(result),
            file_name="session.json"
        )