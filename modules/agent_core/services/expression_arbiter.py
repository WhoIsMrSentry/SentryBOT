"""Compatibility arbitration for competing NeoPixel and OLED expression writers."""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Mapping, Optional

EXPRESSION_IDLE_COMPATIBILITY = True
EXPRESSION_IDLE_BOUNDARY_ROLE = "agent_core_compat_expression_arbiter"
EXPRESSION_IDLE_RUNTIME_OWNER = "central state/output: modules.expression compatibility boundary"


class ExpressionArbiter:
    """Backward-compatible expression owner with policy-driven visual leases."""

    def __init__(self, policy: Optional[Mapping[str, Any]] = None) -> None:
        self._lock = threading.Lock()
        self._policy: Dict[str, Any] = dict(policy) if isinstance(policy, Mapping) else {}
        self._lights_owner = ""
        self._oled_owner = ""
        self._leases: Dict[str, Dict[str, Any]] = {"lights": {}, "oled": {}}

    def _priority_for(self, source: str, requested: Optional[float]) -> float:
        if requested is not None:
            try:
                return float(requested)
            except (TypeError, ValueError):
                return 0.0
        priorities = self._policy.get("priorities", {})
        if isinstance(priorities, Mapping):
            try:
                return float(priorities.get(source, priorities.get("default", 0.0)))
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    def _ttl_for(self, channel: str, requested: Optional[float]) -> float:
        value = requested
        if value is None:
            channels = self._policy.get("channels", {})
            channel_cfg = channels.get(channel, {}) if isinstance(channels, Mapping) else {}
            value = channel_cfg.get("default_lease_s", 0.0) if isinstance(channel_cfg, Mapping) else 0.0
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0

    def _expire_locked(self, channel: str) -> None:
        lease = self._leases.get(channel, {})
        expires_at = float(lease.get("expires_at", 0.0) or 0.0)
        if lease and expires_at > 0.0 and time.monotonic() >= expires_at:
            self._leases[channel] = {}
            if channel == "lights":
                self._lights_owner = ""
            else:
                self._oled_owner = ""

    def _force_allowed(self, source: str) -> bool:
        allowed = self._policy.get("force_sources", [])
        return not allowed or source in allowed

    def _claim(self, channel: str, source: str, force: bool = False, priority: Optional[float] = None, ttl_s: Optional[float] = None, revision: str = "", semantic: str = "") -> bool:
        source = str(source or "").strip()
        if not source:
            return False
        with self._lock:
            self._expire_locked(channel)
            current = self._leases.get(channel, {})
            candidate_priority = self._priority_for(source, priority)
            if current and current.get("source") != source:
                current_priority = float(current.get("priority", 0.0) or 0.0)
                if not force and candidate_priority <= current_priority:
                    return False
                if force and (not self._force_allowed(source) or candidate_priority < current_priority):
                    return False
            ttl = self._ttl_for(channel, ttl_s)
            self._leases[channel] = {
                "source": source,
                "priority": candidate_priority,
                "revision": str(revision or ""),
                "semantic": str(semantic or ""),
                "expires_at": time.monotonic() + ttl if ttl > 0.0 else 0.0,
            }
            if channel == "lights":
                self._lights_owner = source
            else:
                self._oled_owner = source
            return True

    def claim_lights(self, source: str, force: bool = False, *, priority: Optional[float] = None, ttl_s: Optional[float] = None, revision: str = "", semantic: str = "") -> bool:
        return self._claim("lights", source, force, priority, ttl_s, revision, semantic)

    def claim_oled(self, source: str, force: bool = False, *, priority: Optional[float] = None, ttl_s: Optional[float] = None, revision: str = "", semantic: str = "") -> bool:
        return self._claim("oled", source, force, priority, ttl_s, revision, semantic)

    def release(self, source: str) -> None:
        source = str(source or "").strip()
        with self._lock:
            for channel, owner_attr in (("lights", "_lights_owner"), ("oled", "_oled_owner")):
                self._expire_locked(channel)
                if self._leases.get(channel, {}).get("source") == source:
                    self._leases[channel] = {}
                    setattr(self, owner_attr, "")

    def status(self) -> Dict[str, Any]:
        """Legacy compact status retained for existing callers and routes."""
        with self._lock:
            self._expire_locked("lights")
            self._expire_locked("oled")
            return {"lights_owner": self._lights_owner, "oled_owner": self._oled_owner}

    def detailed_status(self) -> Dict[str, Any]:
        with self._lock:
            self._expire_locked("lights")
            self._expire_locked("oled")
            now = time.monotonic()
            leases: Dict[str, Dict[str, Any]] = {}
            for channel, lease in self._leases.items():
                item = dict(lease)
                expires_at = float(item.get("expires_at", 0.0) or 0.0)
                item["remaining_s"] = round(max(0.0, expires_at - now), 3) if expires_at else None
                leases[channel] = item
            return {"owners": {"lights_owner": self._lights_owner, "oled_owner": self._oled_owner}, "leases": leases}
