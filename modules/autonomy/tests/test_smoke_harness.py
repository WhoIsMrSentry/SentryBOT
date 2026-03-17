import time

from modules.autonomy.services.brain import AutonomyBrain


class FakeServiceClient:
    def __init__(self):
        self.calls = []
        self._speech_queue = [
            {"text": "Merhaba, nasılsın?", "final": True, "confidence": 0.98}
        ]
        self._direction_queue = [{"angle": 25}]

    def select_persona(self, name):
        self.calls.append(("select_persona", name))

    def get_speech_direction(self):
        if self._direction_queue:
            return self._direction_queue.pop(0)
        return None

    def get_last_speech(self):
        if self._speech_queue:
            return self._speech_queue.pop(0)
        return {"text": "", "final": False}

    def move_head(self, pan, tilt, speed=0.8):
        self.calls.append(("move_head", pan, tilt))
        return {"ok": True}

    def push_interaction_event(self, ev):
        self.calls.append(("event", ev))

    def speak(self, text, tone=None, engine=None, language=None):
        self.calls.append(("speak", text))
        return {"ok": True}

    def chat(self, query, apply_actions: bool = False, source_lang=None, response_lang=None):
        # simple canned response
        return {"answer": "Ben iyiyim, teşekkürler.", "actions": None}

    def update_emotions(self, emotions):
        self.calls.append(("update_emotions", tuple(emotions)))

    # stub other methods used by AutonomyBrain
    def select_persona(self, name):
        self.calls.append(("select_persona", name))


def test_autonomy_smoke_harness_reacts_to_speech_and_direction():
    cfg = {"defaults": {"loop_interval_ms": 200}, "wikirag": {"enabled": False}, "llm": {"enabled": False}}
    brain = AutonomyBrain(cfg)
    fake = FakeServiceClient()
    # inject fake client
    brain.client = fake

    brain.start()
    try:
        # let the loop run a short time
        time.sleep(1.0)
        # verify that speech reaction produced a speak call
        has_speak = any(c[0] == "speak" for c in fake.calls)
        has_move = any(c[0] == "move_head" for c in fake.calls)
        has_event = any(c[0] == "event" for c in fake.calls)
        assert has_speak or has_move or has_event, f"Expected at least one reaction, got calls: {fake.calls}"
    finally:
        brain.stop()
