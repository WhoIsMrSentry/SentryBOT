from __future__ import annotations

# --- SentryBOT safety/action boundary contract ---
SAFETY_ACTION_COMPATIBILITY = True
SAFETY_ACTION_BOUNDARY_ROLE = 'agent_core_compat_llm_tool_registry'
SAFETY_ACTION_RUNTIME_OWNER = 'robot-runtime capabilities and execution: modules.autonomy'
SAFETY_ACTION_BOUNDARY_REASON = 'ToolRegistry remains an LLM-facing proposal surface. Physical actions must still pass through action/safety/capability paths.'
# --- End SentryBOT safety/action boundary contract ---

from .http_client import HttpClient
from .tool_registry import ToolRegistry

__all__ = [
    "HttpClient",
    "ToolRegistry",
    "SAFETY_ACTION_COMPATIBILITY",
    "SAFETY_ACTION_BOUNDARY_ROLE",
    "SAFETY_ACTION_RUNTIME_OWNER",
    "SAFETY_ACTION_BOUNDARY_REASON",
]
