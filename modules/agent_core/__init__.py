from __future__ import annotations

# Agent core public exports.
#
# Importing this package must not initialize runtime console, hardware paths, or
# agent runtime subsystems. Public symbols are resolved lazily on first access.

from importlib import import_module
from typing import Any

__all__ = [
    "AgentOrchestrator",
    "ActionSafetyFilter",
    "EpisodicMemory",
    "TopologicalMap",
    "ToolRegistry",
    "WorldState",
    "SensorFeedbackLoop",
    "IdleBehaviorSystem",
    "SubAgentProfile",
    "TriLayerRouter",
    "build_subagent_profiles",
]

_LAZY_EXPORTS = {
    "AgentOrchestrator": "modules.agent_core.services.agent:AgentOrchestrator",
    "ActionSafetyFilter": "modules.agent_core.services.safety_filter:ActionSafetyFilter",
    "EpisodicMemory": "modules.agent_core.services.memory:EpisodicMemory",
    "TopologicalMap": "modules.agent_core.services.slam:TopologicalMap",
    "ToolRegistry": "modules.agent_core.services.tools:ToolRegistry",
    "WorldState": "modules.agent_core.services.world_state:WorldState",
    "SensorFeedbackLoop": "modules.agent_core.services.sensor_loop:SensorFeedbackLoop",
    "IdleBehaviorSystem": "modules.agent_core.services.idle_behavior:IdleBehaviorSystem",
    "SubAgentProfile": "modules.agent_core.services.tri_layer:SubAgentProfile",
    "TriLayerRouter": "modules.agent_core.services.tri_layer:TriLayerRouter",
    "build_subagent_profiles": "modules.agent_core.services.tri_layer:build_subagent_profiles",
}


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target.split(":", 1)
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
