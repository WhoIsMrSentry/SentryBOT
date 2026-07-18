"""Vision arbitration for VLM request conflicts."""

from __future__ import annotations

# --- SentryBOT perception/vision boundary contract ---
PERCEPTION_VISION_COMPATIBILITY = True
PERCEPTION_VISION_BOUNDARY_ROLE = 'agent_core_compat_vision_arbiter'
PERCEPTION_VISION_RUNTIME_OWNER = 'raw VLM request ownership should move toward modules.vlm_bridge or gateway; agent_core keeps compatibility gate for current tool/action flow'
PERCEPTION_VISION_BOUNDARY_REASON = 'VisionArbiter is still passed through AgentOrchestrator into ProgressManager and ToolRegistry. Keep public behavior stable before moving arbitration.'
# --- End SentryBOT perception/vision boundary contract ---

import threading
import time
from typing import Dict, Any


class VisionArbiter:
    """Allows at most one active VLM request at a time."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_until = 0.0
        self._active_by = ""

    def acquire(self, source: str, ttl_s: float = 30.0) -> bool:
        now = time.time()
        with self._lock:
            if now < self._active_until:
                return False
            self._active_until = now + max(1.0, float(ttl_s))
            self._active_by = str(source or "")
            return True

    def release(self, source: str = "") -> None:
        with self._lock:
            if source and self._active_by and source != self._active_by:
                return
            self._active_until = 0.0
            self._active_by = ""

    def status(self) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            return {
                "busy": now < self._active_until,
                "source": self._active_by,
                "remaining_s": round(max(0.0, self._active_until - now), 2),
            }

