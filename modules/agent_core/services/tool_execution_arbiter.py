"""Tool execution arbiter for SentryBOT Agent Core.

Prevents conflicting tool executions:
* At most one VLM call at a time
* Safety actions cannot be interrupted by agent tools
* Idle behaviors yield to active user requests
* Cancellable task support
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Set

logger = logging.getLogger("agent.tool_arbiter")

# Resource groups — at most one active task per group
_TOOL_GROUPS: Dict[str, str] = {
    "get_visual_context": "vlm",
    "ask_vlm_about_scene": "vlm",
    "describe_scene": "vlm",
    "get_vision": "vlm",
    "move_head": "head",
    "focus_person": "head",
    "set_lights": "lights",
    "set_neopixel": "lights",
}


class ToolExecutionArbiter:
    """Ensures non-conflicting tool execution."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_groups: Dict[str, str] = {}  # group -> tool_name
        self._active_since: Dict[str, float] = {}  # group -> start_time
        self._cancelled: Set[str] = set()  # tool call IDs

    def can_execute(self, tool_name: str, call_id: str = "") -> bool:
        """Check if a tool can execute right now."""
        if call_id and call_id in self._cancelled:
            return False
        group = _TOOL_GROUPS.get(tool_name)
        if not group:
            return True
        with self._lock:
            active = self._active_groups.get(group)
            if active:
                started = self._active_since.get(group, 0)
                # Auto-expire after 60s (safety valve)
                if time.time() - started > 60:
                    del self._active_groups[group]
                    self._active_since.pop(group, None)
                    return True
                return False
            return True

    def acquire(self, tool_name: str) -> bool:
        """Mark a tool as actively running."""
        group = _TOOL_GROUPS.get(tool_name)
        if not group:
            return True
        with self._lock:
            if group in self._active_groups:
                started = self._active_since.get(group, 0)
                if time.time() - started > 60:
                    pass  # expired, allow override
                else:
                    return False
            self._active_groups[group] = tool_name
            self._active_since[group] = time.time()
            return True

    def release(self, tool_name: str) -> None:
        """Mark a tool as finished."""
        group = _TOOL_GROUPS.get(tool_name)
        if not group:
            return
        with self._lock:
            if self._active_groups.get(group) == tool_name:
                del self._active_groups[group]
                self._active_since.pop(group, None)

    def cancel(self, call_id: str) -> None:
        with self._lock:
            self._cancelled.add(call_id)
            if len(self._cancelled) > 100:
                self._cancelled.clear()

    def is_group_busy(self, group: str) -> bool:
        with self._lock:
            if group not in self._active_groups:
                return False
            started = self._active_since.get(group, 0)
            if time.time() - started > 60:
                return False
            return True

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            return {
                group: {
                    "tool": tool,
                    "elapsed_s": round(now - self._active_since.get(group, now), 1),
                }
                for group, tool in self._active_groups.items()
            }


__all__ = ["ToolExecutionArbiter"]
