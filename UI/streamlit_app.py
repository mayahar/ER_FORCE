import sys
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent
REPO_ROOT = UI_DIR.parent
for path in (str(REPO_ROOT), str(UI_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import streamlit as st
import copy

from core.mock_controller import Controller
from core.subject_repository import update_subject_baseline
from screens import enter_id, questionnaire, game, results
from screens import new_user_sleep_gate
from styles import apply_baseline_saved_theme

st.set_page_config(page_title="Fatigue App", layout="wide")

# ------------------------
# SESSION STATE
# ------------------------
if "controller" not in st.session_state:
    st.session_state.controller = Controller()

if "state" not in st.session_state:
    st.session_state.state = {"screen": "enter_id"}

if "result" not in st.session_state:
    st.session_state.result = None

controller = st.session_state.controller
state = st.session_state.state["screen"]


def render_baseline_saved():
    apply_baseline_saved_theme()

    st.title("שמירת בייסליין")
    st.markdown(
        """
        <div class="baseline-box">
        הבייסליין נשמר בהצלחה. בהרצה הבאה של אותו משתמש תתבצע השוואה מול הבייסליין הזה.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("חזרה למסך פתיחה"):
        st.session_state.state = {"screen": "enter_id"}
        st.session_state.result = None
        st.rerun()

# ------------------------
# ROUTER
# ------------------------
if state == "enter_id":
    enter_id.render(controller)

elif state == "questionnaire":
    questionnaire.render(controller)

elif state == "new_user_sleep_gate":
    new_user_sleep_gate.render(controller)

elif state == "game":
    game.render(controller)

elif state == "baseline_saved":
    render_baseline_saved()

elif state == "result":

    # ------------------------
    # SAFETY CHECK
    # ------------------------
    if controller.subject is None:
        st.error("No subject loaded")
        st.stop()

    if st.session_state.state.get("baseline_capture"):
        eye_features = st.session_state.get("eye_features")
        if eye_features and hasattr(controller, "set_eye_features"):
            controller.set_eye_features(eye_features)

        controller.run_multimodal_game()
        baseline = copy.deepcopy(controller.features)
        subject_id = controller.subject.get("id")

        updated_subject = update_subject_baseline(subject_id, baseline)
        controller.subject = copy.deepcopy(updated_subject)
        controller.compute_fatigue()

        baseline_result = copy.deepcopy(controller.get_result())
        research_context = st.session_state.state.get("research_context")

        if research_context:
            baseline_result["research"] = copy.deepcopy(research_context)
            csv = results.export_result_csv(baseline_result)
            results._save_report_once(subject_id, csv, result=baseline_result)

        st.session_state.result = None
        st.session_state.state["baseline_capture"] = False
        st.session_state.state["screen"] = "baseline_saved"
        st.session_state.fg_pid = 0
        st.session_state.fg_started_at = None
        st.session_state.fg_finished_handled = False
        st.rerun()

    # ------------------------
    # RUN PIPELINE ONCE בלבד
    # ------------------------
    if not st.session_state.result:

        eye_features = st.session_state.get("eye_features")
        if eye_features and hasattr(controller, "set_eye_features"):
            controller.set_eye_features(eye_features)

        controller.run_multimodal_game()
        controller.compute_fatigue()

        # 🔥 חשוב מאוד: freeze snapshot
        st.session_state.result = copy.deepcopy(controller.get_result())

        research_context = st.session_state.state.get("research_context")

        if research_context:
            st.session_state.result["research"] = copy.deepcopy(research_context)

    result = st.session_state.result

    # ------------------------
    # RENDER
    # ------------------------
    results.render(result)
