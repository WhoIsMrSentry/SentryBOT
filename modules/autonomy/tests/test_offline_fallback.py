from __future__ import annotations

from modules.autonomy.services.brain import AutonomyBrain


class _OfflineClient:
    def __init__(self):
        self.spoken = []
        self.events = []
        self.chat_called = 0

    def get_speech_direction(self):
        return None

    def get_last_speech(self):
        return None

    def is_service_available(self, service):
        return False

    def push_interaction_event(self, event_type, data=None):
        self.events.append((event_type, data))

    def speak(self, text, tone=None, engine=None, language=None):
        self.spoken.append(text)
        return {"ok": True}

    def chat(self, query, apply_actions: bool = False, source_lang=None, response_lang=None):
        self.chat_called += 1
        return {"answer": "should-not-happen"}

    def chat_rag(self, query, apply_actions: bool = False):
        self.chat_called += 1
        return {"answer": "should-not-happen"}



def test_offline_fallback_replies_without_llm_call():
    cfg = {
        "defaults": {"loop_interval_ms": 200},
        "llm": {"enabled": True},
        "offline_mode": {
            "enabled": True,
            "availability_ttl_s": 1,
            "fallback_replies": ["Yerel mod cevap"],
        },
        "owner": {"enabled": False},
    }
    brain = AutonomyBrain(cfg)
    client = _OfflineClient()
    brain.client = client

    brain._react_to_speech("Bu nedir?")

    assert client.chat_called == 0
    assert client.spoken and client.spoken[-1] == "Yerel mod cevap"
    assert any(evt[0] == "autonomy.offline" for evt in client.events)


def test_offline_fallback_prefers_persona_replies():
    cfg = {
        "defaults": {"loop_interval_ms": 200, "mood": {"initial_happiness": 90, "initial_energy": 80, "decay_rate": 0.0}},
        "llm": {"enabled": True},
        "offline_mode": {
            "enabled": True,
            "availability_ttl_s": 1,
            "fallback_replies": ["Genel cevap"],
            "persona_replies": {"joy": ["Mutlu yerel cevap"], "neutral": ["Notr yerel cevap"]},
        },
        "owner": {"enabled": False},
    }
    brain = AutonomyBrain(cfg)
    client = _OfflineClient()
    brain.client = client

    brain._react_to_speech("Merhaba")

    assert client.spoken and client.spoken[-1] == "Mutlu yerel cevap"


def test_offline_contextual_replies_override_persona_pool():
    cfg = {
        "defaults": {"loop_interval_ms": 200, "mood": {"initial_happiness": 90, "initial_energy": 80, "decay_rate": 0.0}},
        "llm": {"enabled": True},
        "offline_mode": {
            "enabled": True,
            "contextual_replies": {"question": ["Soru odakli yerel cevap"]},
            "persona_replies": {"joy": ["Mutlu yerel cevap"]},
        },
        "owner": {"enabled": False},
    }
    brain = AutonomyBrain(cfg)
    client = _OfflineClient()
    brain.client = client

    brain._react_to_speech("Bu ne?")

    assert client.spoken and client.spoken[-1] == "Soru odakli yerel cevap"
