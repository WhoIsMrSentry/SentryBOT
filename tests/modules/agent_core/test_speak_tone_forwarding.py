"""The queued `speak` action must forward emotional tone to the arbiter."""

from __future__ import annotations

from typing import Any, Dict

from modules.agent_core.services.action_arbiter import ActionArbiter, ActionRequest
from modules.agent_core.services.agent import AgentOrchestrator
from modules.common.latency_trace import latency_trace


class _RecordingArbiter:
    def __init__(self):
        self.calls = []

    def enqueue(self, **kwargs):
        self.calls.append(kwargs)
        return "id"


def _agent_with_handlers():
    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    agent.action_arbiter = ActionArbiter()
    agent.speech_arbiter = _RecordingArbiter()
    agent._register_action_handlers()
    return agent


def _speak_req(payload: Dict[str, Any]):
    return ActionRequest(type="speak", source="autonomy", priority=50, ttl_ms=10000, payload=payload)


def test_speak_action_forwards_tone():
    agent = _agent_with_handlers()
    agent.action_arbiter.submit(_speak_req({"text": "Merhaba", "tone": "joy"}))
    assert agent.speech_arbiter.calls
    assert agent.speech_arbiter.calls[0]["tone"] == "joy"


def test_speak_action_forwards_dict_tone():
    agent = _agent_with_handlers()
    agent.action_arbiter.submit(_speak_req({"text": "Merhaba", "tone": {"rate": 200}}))
    assert agent.speech_arbiter.calls[0]["tone"] == {"rate": 200}


def test_missing_tone_passes_none():
    agent = _agent_with_handlers()
    agent.action_arbiter.submit(_speak_req({"text": "Merhaba"}))
    assert agent.speech_arbiter.calls[0]["tone"] is None


def test_agent_reads_mood_tone_snapshot():
    agent = AgentOrchestrator.__new__(AgentOrchestrator)

    class Mood:
        def get_speech_tone(self):
            return {"speed": 1.15, "pitch": 1.1, "emotion": "joy"}

    agent.mood_manager = Mood()
    assert agent._current_speech_tone() == {"speed": 1.15, "pitch": 1.1, "emotion": "joy"}


def test_agent_tone_snapshot_falls_back_safely():
    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    assert agent._current_speech_tone() is None

    class BrokenMood:
        def get_speech_tone(self):
            raise RuntimeError("mood unavailable")

    agent.mood_manager = BrokenMood()
    assert agent._current_speech_tone() is None


def test_laya_inference_is_recorded_separately_from_model_ttft():
    agent = AgentOrchestrator.__new__(AgentOrchestrator)

    class Decision:
        inference_ms = 17.5
        target_module = "system2_chat"
        urgency_score = 0.2

    agent._last_laya_fast_path_decision = Decision()
    trace_id = "test-laya-inference-metric"
    latency_trace.ensure(trace_id, {"component": "test"})

    agent._record_laya_latency(trace_id)

    events = latency_trace.get(trace_id)["events"]
    laya_event = next(item for item in events if item["event"] == "laya.inference")
    assert laya_event["data"] == {
        "inference_ms": 17.5,
        "target_module": "system2_chat",
        "urgency": 0.2,
    }
