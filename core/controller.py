import asyncio

from core.reducer import reducer
from core.state import AppState

# integrations (assumed to exist)
from integrations.eye import EyeService
from integrations.audio import AudioService
from integrations.game import GameService

# scoring + data
from scoring.engine import ScoringEngine
from data.persistence import DB


class AppController:

    def __init__(self):
        self.state = AppState.INIT

        self.session = {}
        self.features = {}

        self.eye_service = EyeService()
        self.audio_service = AudioService()
        self.game_service = GameService()

        self.scoring = ScoringEngine()
        self.db = DB()

    # -------------------
    # EVENT HANDLING
    # -------------------
    def dispatch(self, event, payload=None):
        self.state = reducer(self.state, event, payload)

        if payload:
            self.session.update(payload)

    # -------------------
    # MULTIMODAL PIPELINE
    # -------------------
    def run_multimodal_game(self):

        async def _run():
            eye_task = self.eye_service.run()
            audio_task = self.audio_service.run()
            game_task = self.game_service.run()

            eye, audio, game = await asyncio.gather(
                eye_task,
                audio_task,
                game_task
            )

            self.features["eye"] = eye
            self.features["audio"] = audio
            self.features["game"] = game

        asyncio.run(_run())

    # -------------------
    # SCORING
    # -------------------
    def compute_score(self):

        score = self.scoring.compute(
            features=self.features,
            baseline=self.session.get("baseline", {}),
            config={}
        )

        self.session["score"] = score

        return score

    # -------------------
    # RESULT API (for UI)
    # -------------------
    def get_result(self):

        if "score" not in self.session:
            self.compute_score()

        return {
            "score": self.session["score"],
            "breakdown": self.features
        }

    # -------------------
    # SAVE
    # -------------------
    def save_session(self):
        self.db.save_session({
            "session": self.session,
            "features": self.features
        })