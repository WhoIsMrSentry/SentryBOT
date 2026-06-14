"""Phase 3 regression tests: vision arbiter wraps VLM tools, action handlers
covering the new vision actions exist, and ProgressManager exposes a unified
arbiter snapshot."""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import patch

from modules.agent_core.services.action_arbiter import ActionArbiter, ActionRequest
from modules.agent_core.services.expression_arbiter import ExpressionArbiter
from modules.agent_core.services.memory import EpisodicMemory
from modules.agent_core.services.progress import ProgressManager
from modules.agent_core.services.safety_filter import ActionSafetyFilter
from modules.agent_core.services.slam import TopologicalMap
from modules.agent_core.services.tool_execution_arbiter import ToolExecutionArbiter
from modules.agent_core.services.tools import ToolRegistry
from modules.agent_core.services.vision_arbiter import VisionArbiter
from modules.agent_core.services.world_state import WorldState


def _build_registry(vision: VisionArbiter) -> ToolRegistry:
    mem = EpisodicMemory(db_path=":memory:")
    slam = TopologicalMap.__new__(TopologicalMap)
    slam.map_file = "phase3.json"
    slam.nodes = {}
    slam.aliases = {}
    slam.current_location = "base"
    ws = WorldState()
    sf = ActionSafetyFilter()
    return ToolRegistry(None, mem, slam, ws, sf, tool_execution_arbiter=ToolExecutionArbiter(), vision_arbiter=vision)


def test_vision_arbiter_blocks_concurrent_vlm_tools():
    arbiter = VisionArbiter()
    registry = _build_registry(arbiter)

    arbiter.acquire("external", ttl_s=10.0)
    with patch.object(registry, "_vision_input_available", return_value=True):
        result = registry.execute("describe_scene", {})
    assert "vision arbiter busy" in result


def test_action_arbiter_handles_new_vision_types():
    arbiter = ActionArbiter()
    captured: Dict[str, Any] = {}

    def _handler(req: ActionRequest):
        captured["req"] = req
        return {"ok": True}

    arbiter.register_handler("vision_query", _handler)
    arbiter.register_handler("look_around", _handler)
    arbiter.register_handler("face_focus", _handler)
    arbiter.register_handler("face_register", _handler)
    arbiter.register_handler("follow_owner", _handler)
    arbiter.register_handler("stop_follow", _handler)

    for action_type, payload in [
        ("vision_query", {"question": "Who is in front of me?"}),
        ("look_around", {"steps": [{"pan": 60, "tilt": 90}, {"pan": 120, "tilt": 90}]}),
        ("face_focus", {"name": "Emir"}),
        ("face_register", {"name": "Emir", "relationship": "owner", "recognition_level": 5}),
        ("follow_owner", {}),
        ("stop_follow", {}),
    ]:
        captured.clear()
        req = ActionRequest(
            type=action_type,
            source="agent_core",
            priority=70,
            ttl_ms=2000,
            payload=payload,
        )
        result = arbiter.submit(req)
        assert result.get("ok") is True, f"{action_type} -> {result}"
        assert captured.get("req") is not None


def test_progress_manager_arbiter_snapshot_aggregates():
    action_arbiter = ActionArbiter()
    vision_arbiter = VisionArbiter()
    expression_arbiter = ExpressionArbiter()
    tool_arbiter = ToolExecutionArbiter()

    pm = ProgressManager()
    pm.attach_arbiters(
        action_arbiter=action_arbiter,
        vision_arbiter=vision_arbiter,
        expression_arbiter=expression_arbiter,
        tool_execution_arbiter=tool_arbiter,
    )

    vision_arbiter.acquire("source-a", ttl_s=5.0)
    tool_arbiter.acquire("get_visual_context")

    snapshot = pm.arbiter_snapshot()
    assert "timestamp" in snapshot
    assert snapshot["vision"].get("busy") is True
    assert snapshot["tool_execution"].get("vlm", {}).get("tool") == "get_visual_context"
