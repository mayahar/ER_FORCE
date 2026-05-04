import streamlit as st
from state import init_state
from screens import enter_id, questionnaire, game, results

# external controller (assumed existing)
from core.mock_controller import MockController

controller = MockController()

st.set_page_config(page_title="Fatigue App", layout="wide")

if "state" not in st.session_state:
    st.session_state.state = init_state()

state = st.session_state.state["screen"]

# routing
if state == "enter_id":
    enter_id.render(controller)

elif state == "questionnaire":
    questionnaire.render(controller)

elif state == "game":
    game.render(controller)


elif state == "result":
    results.render(controller)

if "controller" not in st.session_state:
    st.session_state.controller = MockController()

controller = st.session_state.controller