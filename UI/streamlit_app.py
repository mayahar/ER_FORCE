import streamlit as st
import copy

from core.mock_controller import Controller
from screens import enter_id, questionnaire, game, results

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

# ------------------------
# ROUTER
# ------------------------
if state == "enter_id":
    enter_id.render(controller)

elif state == "questionnaire":
    questionnaire.render(controller)

elif state == "game":
    game.render(controller)

elif state == "result":

    # ------------------------
    # SAFETY CHECK
    # ------------------------
    if controller.subject is None:
        st.error("No subject loaded")
        st.stop()

    # ------------------------
    # RUN PIPELINE ONCE בלבד
    # ------------------------
    if not st.session_state.result:

        controller.run_multimodal_game()
        controller.compute_fatigue()

        # 🔥 חשוב מאוד: freeze snapshot
        st.session_state.result = copy.deepcopy(controller.get_result())

    result = st.session_state.result

    # ------------------------
    # RENDER
    # ------------------------
    results.render(result)