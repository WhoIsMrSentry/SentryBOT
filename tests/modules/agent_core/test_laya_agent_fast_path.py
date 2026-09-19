"""Agent adapter contract for Laya System 1 fast-path decisions."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from modules.agent_core.services.agent import AgentOrchestrator
from modules.agent_core.services.laya_action_contract import validate_laya_action_proposal


def _agent_with_laya(decision, *, is_fast):
    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    agent.fast_path_enabled = True
    agent.fast_path_max_chars = 200
    agent.world_state = MagicMock()
    agent.world_state.get_state.return_value = {"battery_percent": 80}
    agent.world_state.get_laya_scene_summary.return_value = "desk and lamp"
    agent.tool_registry = MagicMock()
    agent.laya_engine = MagicMock()
    agent.laya_engine.enabled = True
    agent.laya_engine.should_fast_path.return_value = (is_fast, decision)
    return agent


def test_agent_caches_laya_fast_path_decision_without_dispatching_tool():
    decision = SimpleNamespace(is_direct_command=True, suggested_tool="neopixel")
    agent = _agent_with_laya(decision, is_fast=True)

    assert agent._should_fast_path("Işıkları mavi yap")

    assert agent._last_laya_fast_path_decision is decision
    agent.laya_engine.should_fast_path.assert_called_once_with(
        "Işıkları mavi yap",
        world_state={"battery_percent": 80},
        visual_context="desk and lamp",
    )
    agent.tool_registry.execute.assert_not_called()


def test_agent_keeps_laya_conversation_on_system2_even_when_prompt_is_short():
    decision = SimpleNamespace(is_direct_command=False, suggested_tool=None)
    agent = _agent_with_laya(decision, is_fast=False)

    assert not agent._should_fast_path("Nasılsın?")

    assert agent._last_laya_fast_path_decision is decision
    agent.laya_engine.should_fast_path.assert_called_once()
    agent.tool_registry.execute.assert_not_called()


def test_agent_binds_laya_proposal_to_internal_request_not_trace_metadata():
    decision = SimpleNamespace(suggested_action={
        "schema_version": 1,
        "tool_name": "set_lights",
        "arguments": {"color": "blue", "effect": "SOLID"},
        "confidence": 0.94,
    })
    request_id = "internal-turn-uuid"
    caller_trace_id = "caller-controlled-trace"

    AgentOrchestrator._bind_laya_action_request(decision, request_id)

    assert decision.suggested_action["request_id"] == request_id
    assert decision.suggested_action["request_id"] != caller_trace_id
    assert validate_laya_action_proposal(
        decision.suggested_action,
        expected_request_id=request_id,
        policy={
            "enabled": True,
            "allowed_actions": ["set_lights"],
            "confidence_threshold": 0.85,
        },
    )
