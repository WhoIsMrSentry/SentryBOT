"""Speaker identity bridges from autonomy into agent step and consolidation."""

from __future__ import annotations

from modules.agent_core.services.agent import AgentOrchestrator
from modules.agent_core.services.world_state import WorldState


def test_step_sets_world_state_speaker():
    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    agent.world_state = WorldState()
    agent.is_busy = False
    agent.last_run = 0
    agent.cooldown = 0
    agent.tool_registry = type("T", (), {"status_hook": None})()
    agent.progress_manager = type(
        "P",
        (),
        {
            "new_request": staticmethod(lambda **k: "tok"),
            "clear_request": staticmethod(lambda *a, **k: None),
            "emit_final": staticmethod(lambda *a, **k: None),
        },
    )()
    agent._active_progress_token = None
    agent._normalize_session_language = lambda lang: lang or "tr"  # type: ignore
    try:
        agent.step("hello", speaker="Emir")
    except Exception:
        pass
    assert agent.world_state.state.get("speaker") == "Emir"


def test_current_speaker_reads_world_state():
    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    agent.world_state = WorldState()
    agent.world_state.update_state({"speaker": "Zeynep"})
    assert agent._current_speaker() == "Zeynep"
