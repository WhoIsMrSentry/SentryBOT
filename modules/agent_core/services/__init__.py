from __future__ import annotations

# Agent core services public exports.
#
# This module intentionally uses lazy exports. Importing modules.agent_core.services
# or a lightweight submodule such as modules.agent_core.services.memory must not
# initialize the runtime console.

from importlib import import_module
from typing import Any

__all__ = [
    "AgentOrchestrator",
    "EpisodicMemory",
    "TopologicalMap",
    "ToolRegistry",
    "WorldState",
    "ActionSafetyFilter",
    "SensorFeedbackLoop",
    "IdleBehaviorSystem",
    "SubAgentProfile",
    "TriLayerRouter",
    "build_subagent_profiles",
]

_LAZY_EXPORTS = {
    "AgentOrchestrator": ".agent:AgentOrchestrator",
    "EpisodicMemory": ".memory:EpisodicMemory",
    "TopologicalMap": ".slam:TopologicalMap",
    "ToolRegistry": ".tools:ToolRegistry",
    "WorldState": ".world_state:WorldState",
    "ActionSafetyFilter": ".safety_filter:ActionSafetyFilter",
    "SensorFeedbackLoop": ".sensor_loop:SensorFeedbackLoop",
    "IdleBehaviorSystem": ".idle_behavior:IdleBehaviorSystem",
    "SubAgentProfile": ".tri_layer:SubAgentProfile",
    "TriLayerRouter": ".tri_layer:TriLayerRouter",
    "build_subagent_profiles": ".tri_layer:build_subagent_profiles",
}


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target.split(":", 1)
    value = getattr(import_module(module_name, __name__), attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
