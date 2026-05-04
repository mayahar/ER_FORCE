import time
import random


class MockController:

    def __init__(self):
        self.session = {}
        self.features = {}

    # -------------------
    # EVENTS
    # -------------------
    def dispatch(self, event, payload=None):
        if payload:
            self.session.update(payload)

    # -------------------
    # MULTIMODAL GAME (FAKE)
    # -------------------
    def run_multimodal_game(self):
        time.sleep(2)  # simulate loading

        self.features["eye"] = {
            "blink_rate": random.uniform(10, 25),
            "saccades": random.uniform(100, 300)
        }

        self.features["audio"] = {
            "pitch": random.uniform(100, 200),
            "jitter": random.uniform(0.1, 1.0)
        }

        self.features["game"] = {
            "score": random.randint(50, 100),
            "reaction_time": random.uniform(0.2, 1.0)
        }

    # -------------------
    # RESULT
    # -------------------
    def get_result(self):

        score = random.randint(30, 90)

        return {
            "score": score,
            "breakdown": self.features
        }