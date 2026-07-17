"""Request gate for expensive visual language model calls.

The gate separates cheap cache/status polling from expensive semantic VLM work.
It is intentionally dependency-free so it can run on the robot and on a PC test
machine.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason: str
    request_id: str = ""
    priority: str = "normal"
    mode: str = "denied"
    detail: str = ""
    wait_s: float = 0.0
    use_cache: bool = False
    cache_age_s: Optional[float] = None


class VisionRequestGate:
    """Small policy object that throttles expensive VLM requests."""

    DEFAULT_REASON_COOLDOWNS = {
        "user_question": 0.0,
        "hazard": 2.0,
        "new_person": 12.0,
        "owner_seen": 18.0,
        "scene_change": 15.0,
        "sudden_motion": 20.0,
        "boredom": 45.0,
        "idle_refresh": 60.0,
        "manual_refresh": 10.0,
        "background_refresh": 30.0,
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None, *, context_max_age_s: float = 45.0) -> None:
        cfg = dict(config or {})
        self.enabled = bool(cfg.get("enabled", True))
        self.max_inflight = max(1, int(cfg.get("max_inflight", 1)))
        self.cache_ttl_s = float(cfg.get("cache_ttl_s", context_max_age_s))
        self.default_cooldown_s = float(cfg.get("default_cooldown_s", 30.0))
        self.log_decisions = bool(cfg.get("log_decisions", True))
        reason_cfg = cfg.get("reason_cooldowns_s", {})
        self.reason_cooldowns_s = dict(self.DEFAULT_REASON_COOLDOWNS)
        if isinstance(reason_cfg, dict):
            for key, value in reason_cfg.items():
                try:
                    self.reason_cooldowns_s[str(key)] = float(value)
                except Exception:
                    continue
        self._lock = threading.Lock()
        self._inflight: Dict[str, Dict[str, Any]] = {}
        self._last_by_reason: Dict[str, float] = {}
        self._last_by_scene: Dict[str, float] = {}
        self._counter = 0
        self._stats = {
            "approved": 0,
            "denied": 0,
            "cache": 0,
            "finished_ok": 0,
            "finished_error": 0,
        }

    def _cooldown_for(self, reason: str) -> float:
        return float(self.reason_cooldowns_s.get(reason, self.default_cooldown_s))

    def decide(
        self,
        *,
        reason: str,
        priority: str = "normal",
        scene_key: str = "",
        force: bool = False,
        has_cache: bool = False,
        cache_age_s: Optional[float] = None,
        now: Optional[float] = None,
    ) -> GateDecision:
        now = time.time() if now is None else float(now)
        reason = str(reason or "background_refresh")
        priority = str(priority or "normal")
        scene_key = str(scene_key or "")
        cache_fresh = bool(has_cache and cache_age_s is not None and float(cache_age_s) <= self.cache_ttl_s)

        if not self.enabled:
            self._counter += 1
            request_id = f"vlm-{int(now * 1000)}-{self._counter}"
            return GateDecision(True, reason, request_id, priority, "disabled", "gate disabled")

        with self._lock:
            if len(self._inflight) >= self.max_inflight:
                self._stats["denied"] += 1
                if cache_fresh:
                    self._stats["cache"] += 1
                return GateDecision(
                    False,
                    reason,
                    priority=priority,
                    mode="inflight",
                    detail="another VLM request is already running",
                    use_cache=cache_fresh,
                    cache_age_s=cache_age_s,
                )

            cooldown_s = 0.0 if force else self._cooldown_for(reason)
            last_reason = self._last_by_reason.get(reason, 0.0)
            elapsed_reason = now - last_reason if last_reason else 999999.0
            last_scene = self._last_by_scene.get(scene_key, 0.0) if scene_key else 0.0
            elapsed_scene = now - last_scene if last_scene else 999999.0
            remaining_reason = max(0.0, cooldown_s - elapsed_reason)
            remaining_scene = max(0.0, min(cooldown_s, self.cache_ttl_s) - elapsed_scene) if scene_key else 0.0
            wait_s = max(remaining_reason, remaining_scene)

            if wait_s > 0.0 and not force:
                self._stats["denied"] += 1
                if cache_fresh:
                    self._stats["cache"] += 1
                return GateDecision(
                    False,
                    reason,
                    priority=priority,
                    mode="cooldown",
                    detail="cooldown active",
                    wait_s=round(wait_s, 2),
                    use_cache=cache_fresh,
                    cache_age_s=cache_age_s,
                )

            self._counter += 1
            request_id = f"vlm-{int(now * 1000)}-{self._counter}"
            self._last_by_reason[reason] = now
            if scene_key:
                self._last_by_scene[scene_key] = now
            self._stats["approved"] += 1
            return GateDecision(True, reason, request_id, priority, "approved", "approved")

    def mark_start(self, request_id: str, *, reason: str = "", priority: str = "") -> None:
        if not request_id:
            return
        with self._lock:
            self._inflight[request_id] = {"started_at": time.time(), "reason": reason, "priority": priority}

    def mark_finish(self, request_id: str, *, ok: bool = True) -> None:
        if not request_id:
            return
        with self._lock:
            self._inflight.pop(request_id, None)
            self._stats["finished_ok" if ok else "finished_error"] += 1

    def record_manual_event(self, reason: str, *, ok: bool = True) -> None:
        now = time.time()
        with self._lock:
            self._last_by_reason[str(reason or "manual_refresh")] = now
            self._stats["finished_ok" if ok else "finished_error"] += 1

    @property
    def inflight_count(self) -> int:
        with self._lock:
            return len(self._inflight)

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.enabled,
                "max_inflight": self.max_inflight,
                "inflight": len(self._inflight),
                "cache_ttl_s": self.cache_ttl_s,
                "reason_cooldowns_s": dict(self.reason_cooldowns_s),
                "stats": dict(self._stats),
                "last_by_reason": {k: round(time.time() - v, 1) for k, v in self._last_by_reason.items()},
            }


__all__ = ["VisionRequestGate", "GateDecision"]
