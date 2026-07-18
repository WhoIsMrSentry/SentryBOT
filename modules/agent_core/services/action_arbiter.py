"""Central action arbitration for SentryBOT.

Every physical or behavioural action (head move, speak, lights, VLM call, …)
is submitted here as an ``ActionRequest``.  The arbiter enforces:

* strict priority ordering
* TTL expiry (stale requests are dropped)
* cooldown per ``cooldown_key`` (prevents spam)
* payload dedup (identical payloads within a window are suppressed)
* single-writer guarantees for exclusive resources (e.g. TTS, VLM)
"""

from __future__ import annotations

# --- SentryBOT safety/action boundary contract ---
SAFETY_ACTION_COMPATIBILITY = True
SAFETY_ACTION_BOUNDARY_ROLE = 'agent_core_compat_action_arbiter'
SAFETY_ACTION_RUNTIME_OWNER = 'robot-runtime execution and capability approval: modules.autonomy'
SAFETY_ACTION_BOUNDARY_REASON = 'ActionArbiter is still used by AgentOrchestrator and agent_core action API as an LLM/tool proposal arbitration surface. Keep stable until callers are migrated.'
# --- End SentryBOT safety/action boundary contract ---

import hashlib
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("agent.action_arbiter")


# ── Priority constants ────────────────────────────────────────────────
class ActionPriority(IntEnum):
    IDLE = 20
    AUTONOMY_IDLE = 30
    GENERAL_SCENE = 35
    VLM_INTEREST = 50
    FRIEND = 60
    AGENT_TOOL = 65
    FAMILY = 70
    ACTIVE_SPEAKER = 75
    OWNER_FOLLOW = 85
    SAFETY = 95
    MANUAL = 100


# ── Source labels ─────────────────────────────────────────────────────
VALID_SOURCES = frozenset({
    "manual", "safety", "agent_core", "vlm_bridge",
    "autonomy", "speech", "wakeword", "scheduler",
    "owner_follow", "active_speaker",
})

# ── Action types ──────────────────────────────────────────────────────
VALID_ACTION_TYPES = frozenset({
    "head_move", "speak", "listen", "vision_capture",
    "vision_vlm_call", "vision_query", "lights", "oled_face", "animation",
    "sound", "follow", "follow_owner", "stop_follow", "look_around",
    "face_register", "face_focus", "idle_behavior", "tool_call", "notification",
})

# Exclusive resource groups – at most one active action per group.
_EXCLUSIVE_GROUPS: Dict[str, str] = {
    "speak": "tts",
    "vision_vlm_call": "vlm",
    "vision_query": "vlm",
    "head_move": "head",
    "look_around": "head",
    "face_focus": "head",
    "follow_owner": "head",
    "stop_follow": "head",
}


@dataclass
class ActionRequest:
    """A single action submitted to the arbiter."""

    action_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    type: str = "unknown"
    source: str = "autonomy"
    priority: int = 30
    ttl_ms: int = 5000
    cooldown_key: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0

    def __post_init__(self) -> None:
        if self.expires_at <= 0.0:
            self.expires_at = self.created_at + (self.ttl_ms / 1000.0)

    @property
    def expired(self) -> bool:
        return time.time() > self.expires_at

    def payload_hash(self) -> str:
        raw = json.dumps(self.payload, sort_keys=True, default=str)
        return hashlib.md5(raw.encode()).hexdigest()[:10]


class ActionArbiter:
    """Thread-safe central arbiter for all robot actions."""

    def __init__(
        self,
        default_cooldown_s: float = 0.5,
        dedup_window_s: float = 2.0,
    ) -> None:
        self._lock = threading.Lock()
        self._default_cooldown_s = max(0.1, float(default_cooldown_s))
        self._dedup_window_s = max(0.2, float(dedup_window_s))

        # cooldown_key -> expiry timestamp
        self._cooldowns: Dict[str, float] = {}
        # (type, payload_hash) -> timestamp of last dispatch
        self._recent_dispatches: Dict[str, float] = {}
        # resource_group -> (source, expiry)
        self._exclusive_locks: Dict[str, tuple] = {}
        # registered dispatch callbacks: type -> callable
        self._dispatch_handlers: Dict[str, Callable[[ActionRequest], Any]] = {}
        # cancelled action IDs
        self._cancelled: set = set()

    # ── Registration ──────────────────────────────────────────────────
    def register_handler(
        self, action_type: str, handler: Callable[[ActionRequest], Any]
    ) -> None:
        self._dispatch_handlers[action_type] = handler

    # ── Submit ────────────────────────────────────────────────────────
    def submit(self, request: ActionRequest) -> Dict[str, Any]:
        """Submit an action request.  Returns status dict."""
        with self._lock:
            return self._evaluate(request)

    def cancel(self, action_id: str) -> bool:
        with self._lock:
            self._cancelled.add(action_id)
            return True

    def cancel_by_source(self, source: str) -> int:
        """Cancel all pending actions from a source (best effort)."""
        # Since we dispatch immediately, this mainly clears exclusive locks.
        count = 0
        with self._lock:
            for group, (locked_source, _exp) in list(self._exclusive_locks.items()):
                if locked_source == source:
                    del self._exclusive_locks[group]
                    count += 1
        return count

    # ── Query ─────────────────────────────────────────────────────────
    def get_exclusive_status(self) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            result = {}
            for group, (src, exp) in self._exclusive_locks.items():
                result[group] = {
                    "source": src,
                    "expires_in_s": round(max(0, exp - now), 2),
                    "active": exp > now,
                }
            return result

    # ── Internal ──────────────────────────────────────────────────────
    def _evaluate(self, req: ActionRequest) -> Dict[str, Any]:
        now = time.time()

        # 1. Check cancellation
        if req.action_id in self._cancelled:
            self._cancelled.discard(req.action_id)
            return {"ok": False, "reason": "cancelled"}

        # 2. TTL check
        if req.expired:
            return {"ok": False, "reason": "expired"}

        # 3. Cooldown check
        if req.cooldown_key:
            until = self._cooldowns.get(req.cooldown_key, 0.0)
            if now < until:
                return {"ok": False, "reason": "cooldown", "retry_after_s": round(until - now, 2)}

        # 4. Payload dedup
        dedup_key = f"{req.type}:{req.payload_hash()}"
        last = self._recent_dispatches.get(dedup_key, 0.0)
        if now - last < self._dedup_window_s:
            return {"ok": False, "reason": "duplicate"}

        # 5. Exclusive resource check
        group = _EXCLUSIVE_GROUPS.get(req.type)
        if group:
            locked = self._exclusive_locks.get(group)
            if locked:
                locked_source, locked_exp = locked
                if locked_exp > now:
                    # Compare priority – higher wins
                    locked_priority = self._source_base_priority(locked_source)
                    if req.priority < locked_priority:
                        return {
                            "ok": False,
                            "reason": "resource_locked",
                            "group": group,
                            "locked_by": locked_source,
                        }
                    # Higher priority request overrides
                    logger.info(
                        "Action %s overrides %s lock on '%s' (pri %d > %d)",
                        req.action_id, locked_source, group,
                        req.priority, locked_priority,
                    )
            # Acquire lock
            self._exclusive_locks[group] = (req.source, req.expires_at)

        # 6. Dispatch
        self._recent_dispatches[dedup_key] = now
        if req.cooldown_key:
            self._cooldowns[req.cooldown_key] = now + self._default_cooldown_s

        # Garbage-collect old entries periodically
        if len(self._recent_dispatches) > 200:
            self._gc(now)

        handler = self._dispatch_handlers.get(req.type)
        dispatch_result = None
        if handler:
            try:
                dispatch_result = handler(req)
            except Exception as exc:
                logger.warning("Action handler for '%s' failed: %s", req.type, exc)
                return {"ok": False, "reason": "handler_error", "error": str(exc)}

        logger.debug(
            "Action dispatched: type=%s source=%s pri=%d id=%s",
            req.type, req.source, req.priority, req.action_id,
        )
        return {"ok": True, "action_id": req.action_id, "result": dispatch_result}

    def release_exclusive(self, group: str) -> None:
        """Manually release an exclusive resource lock."""
        with self._lock:
            self._exclusive_locks.pop(group, None)

    @staticmethod
    def _source_base_priority(source: str) -> int:
        _MAP = {
            "manual": ActionPriority.MANUAL,
            "safety": ActionPriority.SAFETY,
            "owner_follow": ActionPriority.OWNER_FOLLOW,
            "active_speaker": ActionPriority.ACTIVE_SPEAKER,
            "agent_core": ActionPriority.AGENT_TOOL,
            "vlm_bridge": ActionPriority.VLM_INTEREST,
            "autonomy": ActionPriority.AUTONOMY_IDLE,
            "scheduler": ActionPriority.AUTONOMY_IDLE,
            "speech": ActionPriority.ACTIVE_SPEAKER,
            "wakeword": ActionPriority.ACTIVE_SPEAKER,
        }
        return _MAP.get(source, ActionPriority.IDLE)

    def _gc(self, now: float) -> None:
        cutoff = now - self._dedup_window_s * 3
        self._recent_dispatches = {
            k: v for k, v in self._recent_dispatches.items() if v > cutoff
        }
        self._cooldowns = {k: v for k, v in self._cooldowns.items() if v > now}
        expired_groups = [
            g for g, (_, exp) in self._exclusive_locks.items() if exp <= now
        ]
        for g in expired_groups:
            del self._exclusive_locks[g]
        if len(self._cancelled) > 100:
            self._cancelled.clear()


__all__ = ["ActionArbiter", "ActionRequest", "ActionPriority"]
