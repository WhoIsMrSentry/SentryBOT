# Services namespace — re-exports core components for xAgentCoreService.
# Agent Core files live at module root (agent.py, memory.py, etc.)
# This proxy keeps the xService pattern consistent with other modules.

from .agent import AgentOrchestrator
from .memory import EpisodicMemory
from .slam import TopologicalMap
from .tools import ToolRegistry
from .world_state import WorldState
from .safety_filter import ActionSafetyFilter
from .sensor_loop import SensorFeedbackLoop
from .idle_behavior import IdleBehaviorSystem

__all__ = [
    "AgentOrchestrator",
    "EpisodicMemory",
    "TopologicalMap",
    "ToolRegistry",
    "WorldState",
    "ActionSafetyFilter",
    "SensorFeedbackLoop",
    "IdleBehaviorSystem",
]
