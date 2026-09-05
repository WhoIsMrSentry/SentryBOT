"""Single write gate (tek kapı) for LED/OLED visual channels.

Canonical home of the expression lease policy shared by gateway, agent_core,
autonomy, interactions, neopixel and oled_faces writers (R6/R7/R28/R29).
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Mapping, Optional, Tuple

# Canonical single-int priority scale (agent_core/config/config.yml:expression_lease
# is the persisted mirror of this table — keep both in sync).
CANONICAL_PRIORITIES: Dict[str, int] = {
    "default": 10,
    "ambient_idle": 10,
    "autonomy": 20,
    "interactions": 40,
    "animate": 50,
    "vlm": 60,
    "semantic": 60,
    "owner_command": 80,
    "safety_navigation": 90,
    "hardware_protection": 90,
    "emergency": 100,
}

FORCE_SOURCES: Tuple[str, ...] = ("hardware_protection", "emergency")

DEFAULT_CHANNEL_LEASE_S: Dict[str, float] = {"lights": 2.5, "oled": 2.5}

_PRIORITY_BANDS: Tuple[int, ...] = tuple(
    sorted({int(v) for v in CANONICAL_PRIORITIES.values()})
)


def to_canonical_priority(internal: float) -> int:
    """Snap a legacy internal scale value (e.g. FaceCoordinator 0-100) onto the
    canonical band set so every channel arbitrates on one int scale (R7/R35)."""
    try:
        value = float(internal)
    except (TypeError, ValueError):
        return CANONICAL_PRIORITIES["default"]
    best = _PRIORITY_BANDS[0]
    best_diff = abs(value - best)
    for band in _PRIORITY_BANDS[1:]:
        diff = abs(value - band)
        if diff < best_diff:
            best, best_diff = band, diff
    return best


class LedWritePolicy:
    """Policy-driven visual lease manager for NeoPixel and OLED writers.

    Thread-safe; per-channel single owner with TTL expiry and priority
    preemption. Same surface as the historical ExpressionLeaseManager plus a
    generic ``claim`` entry point.
    """

    def __init__(self, policy: Optional[Mapping[str, Any]] = None) -> None:
        self._lock = threading.Lock()
        self._policy: Dict[str, Any] = dict(policy) if isinstance(policy, Mapping) else {}
        self._lights_owner = ""
        self._oled_owner = ""
        self._leases: Dict[str, Dict[str, Any]] = {"lights": {}, "oled": {}}

    # ── configuration helpers ────────────────────────────────────────────
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
        try:
            return float(CANONICAL_PRIORITIES.get(source, CANONICAL_PRIORITIES["default"]))
        except (TypeError, ValueError):
            return 0.0

    def _ttl_for(self, channel: str, requested: Optional[float]) -> float:
        value = requested
        if value is None:
            channels = self._policy.get("channels", {})
            channel_cfg = channels.get(channel, {}) if isinstance(channels, Mapping) else {}
            value = channel_cfg.get("default_lease_s", 0.0) if isinstance(channel_cfg, Mapping) else 0.0
            if value in (None, 0.0, 0):
                value = DEFAULT_CHANNEL_LEASE_S.get(channel, 0.0)
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0

    # ── lease internals ──────────────────────────────────────────────────
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

    def _claim(
        self,
        channel: str,
        source: str,
        force: bool = False,
        priority: Optional[float] = None,
        ttl_s: Optional[float] = None,
        revision: str = "",
        semantic: str = "",
    ) -> bool:
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

    # ── public API ───────────────────────────────────────────────────────
    def claim(
        self,
        source: str,
        *,
        channel: str = "lights",
        force: bool = False,
        priority: Optional[float] = None,
        ttl_s: Optional[float] = None,
        revision: str = "",
        semantic: str = "",
    ) -> bool:
        channel = "oled" if str(channel).strip().lower() == "oled" else "lights"
        return self._claim(
            channel, source, force, priority, ttl_s, revision, semantic,
        )

    def claim_lights(
        self,
        source: str,
        force: bool = False,
        *,
        priority: Optional[float] = None,
        ttl_s: Optional[float] = None,
        revision: str = "",
        semantic: str = "",
    ) -> bool:
        return self._claim("lights", source, force, priority, ttl_s, revision, semantic)

    def claim_oled(
        self,
        source: str,
        force: bool = False,
        *,
        priority: Optional[float] = None,
        ttl_s: Optional[float] = None,
        revision: str = "",
        semantic: str = "",
    ) -> bool:
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
            return {
                "owners": {"lights_owner": self._lights_owner, "oled_owner": self._oled_owner},
                "leases": leases,
            }


_SHARED_LOCK = threading.Lock()
_SHARED_POLICY: Optional[LedWritePolicy] = None


def get_shared_policy(policy_cfg: Optional[Mapping[str, Any]] = None) -> LedWritePolicy:
    """Return the process-wide policy instance (tek kapı).

    The first caller may inject the ``expression_lease`` config section;
    later callers receive the already-configured singleton regardless of the
    argument so gateway / agent_core / autonomy all share one arbiter.
    """
    global _SHARED_POLICY
    with _SHARED_LOCK:
        if _SHARED_POLICY is None:
            cfg = dict(policy_cfg) if isinstance(policy_cfg, Mapping) else {}
            if not cfg.get("priorities"):
                cfg["priorities"] = dict(CANONICAL_PRIORITIES)
            if not cfg.get("channels"):
                cfg["channels"] = {k: {"default_lease_s": v} for k, v in DEFAULT_CHANNEL_LEASE_S.items()}
            if not cfg.get("force_sources"):
                cfg["force_sources"] = list(FORCE_SOURCES)
            _SHARED_POLICY = LedWritePolicy(cfg)
        return _SHARED_POLICY


def reset_shared_policy() -> None:
    """Test/teardown helper: drop the singleton so the next call reconfigures."""
    global _SHARED_POLICY
    with _SHARED_LOCK:
        _SHARED_POLICY = None
