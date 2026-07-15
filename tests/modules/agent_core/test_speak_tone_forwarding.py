"""The queued `speak` action must forward emotional tone to the arbiter."""

from __future__ import annotations

from typing import Any, Dict

from modules.agent_core.services.action_arbiter import ActionArbiter, ActionRequest
from modules.agent_core.services.agent import AgentOrchestrator


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
