from types import SimpleNamespace

from modules.autonomy.services.brain_parts.decision import DecisionMixin
from modules.autonomy.services.spinal_cord_reflex import SpinalCordReflexEngine


class _Client:
    def __init__(self):
        self.events = []

    def push_interaction_event(self, event, payload=None):
        self.events.append((event, payload or {}))

    def update_emotions(self, _emotions):
        pass


class _Memory:
    def add_event(self, _event):
        pass


class _Laya:
    enabled = True
    _is_available = True

    def __init__(self, decision):
        self.decision = decision

    def decide_with_context(self, _text, **_kwargs):
        return self.decision

    @staticmethod
    def is_emergency_decision(decision):
        return decision.is_emergency

    @staticmethod
    def is_urgent(decision):
        return decision.urgency_score >= 1.5

    @staticmethod
    def get_mood_deltas(_decision):
        return {}


class _Mood:
    def modify(self, *_args):
        pass


def test_laya_emergency_reaches_spinal_cord_motor_stop():
    client = _Client()
    decision = SimpleNamespace(
        is_emergency=True,
        urgency_score=2.8,
        target_module="emergency_stop",
        affective_event="neutral",
    )
    brain = DecisionMixin()
    brain.laya_engine = _Laya(decision)
    brain.state = {"last_speech_text": "Dur!"}
    brain.scene_register = None
    brain.spinal_cord = SpinalCordReflexEngine(
        {"enabled": True, "cooldown_s": 0.0}, client, _Memory()
    )
    brain.mood = _Mood()
    brain.client = client
    brain.memory = _Memory()

    brain._think_laya_reflexes()

    assert ("motor.stop", {"priority": "emergency", "source": "laya_voice"}) in client.events
    assert brain.state["laya_last_high_urgency"] is True
    assert brain.state["laya_last_decision_ts"] > 0


def test_non_emergency_laya_decision_does_not_stop_motor():
    client = _Client()
    decision = SimpleNamespace(
        is_emergency=False,
        urgency_score=0.2,
        target_module="system2_chat",
        affective_event="neutral",
    )
    brain = DecisionMixin()
    brain.laya_engine = _Laya(decision)
    brain.state = {"last_speech_text": "Nasılsın?"}
    brain.scene_register = None
    brain.spinal_cord = SpinalCordReflexEngine(
        {"enabled": True, "cooldown_s": 0.0}, client, _Memory()
    )
    brain.mood = _Mood()
    brain.client = client
    brain.memory = _Memory()

    brain._think_laya_reflexes()

    assert not any(event == "motor.stop" for event, _payload in client.events)
    assert brain.state["laya_last_high_urgency"] is False
