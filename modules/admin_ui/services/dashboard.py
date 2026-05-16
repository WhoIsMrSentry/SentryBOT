"""Aggregates live status snapshots from the various subsystems.

The :class:`DashboardAggregator` does not own any state; it queries already
running services (passed in via ``started``) and produces JSON-serialisable
payloads consumed by both the polling REST endpoints and the SSE stream.

It is intentionally defensive: every accessor catches ``Exception`` so a
single misbehaving subsystem never breaks the dashboard.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("admin_ui.dashboard")


def _safe_call(fn, default=None):
    if not callable(fn):
        return default
    try:
        return fn()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("dashboard accessor failed: %s", exc)
        return default


class DashboardAggregator:
    def __init__(self, started: Dict[str, Any]):
        self.started = started

    # ------------------------------------------------------------------
    # Module accessors
    # ------------------------------------------------------------------
    def _agent(self) -> Optional[Any]:
        agent = self.started.get("agent_core")
        if agent is None:
            autonomy = self.started.get("autonomy")
            brain = getattr(autonomy, "brain", None) if autonomy is not None else None
            agent = getattr(brain, "agent", None) if brain is not None else None
        return agent

    def _progress(self) -> Optional[Any]:
        agent = self._agent()
        return getattr(agent, "progress", None) if agent is not None else None

    def _vlm_bridge(self) -> Optional[Any]:
        return self.started.get("vlm_bridge")

    def _runtime_registry(self) -> Optional[Any]:
        return self.started.get("runtime_registry")

    def _social_db(self) -> Optional[Any]:
        return self.started.get("social_db")

    def _state_manager(self) -> Optional[Any]:
        return self.started.get("state_manager")

    def _imx500_runner(self) -> Optional[Any]:
        return self.started.get("imx500_runner")

    def _onsensor_bus(self) -> Optional[Any]:
        return self.started.get("onsensor_bus")

    # ------------------------------------------------------------------
    # Snapshot builders
    # ------------------------------------------------------------------
    def status_snapshot(self) -> Dict[str, Any]:
        progress = self._progress()
        arbiters: Dict[str, Any] = {}
        if progress is not None and hasattr(progress, "arbiter_snapshot"):
            try:
                arbiters = progress.arbiter_snapshot() or {}
            except Exception as exc:
                logger.debug("arbiter_snapshot failed: %s", exc)

        operational = "unknown"
        state_mgr = self._state_manager()
        if state_mgr is not None:
            operational = _safe_call(getattr(state_mgr, "get_operational", None), default="unknown") or "unknown"

        imx_runner = self._imx500_runner()
        imx_status: Dict[str, Any] = {"available": False}
        if imx_runner is not None:
            imx_status = {
                "available": bool(getattr(imx_runner, "available", False)),
                "running": bool(getattr(imx_runner, "_thread", None) and imx_runner._thread.is_alive()),
            }

        bus = self._onsensor_bus()
        bus_stats = _safe_call(getattr(bus, "stats", None), default={}) if bus is not None else {}

        autonomy = self.started.get("autonomy")
        mood = None
        brain = getattr(autonomy, "brain", None) if autonomy is not None else None
        if brain is not None:
            mood_state = _safe_call(getattr(getattr(brain, "mood", None), "snapshot", None), default=None)
            if mood_state is not None:
                mood = mood_state

        return {
            "ts": time.time(),
            "operational": operational,
            "arbiters": arbiters,
            "mood": mood,
            "imx500": imx_status,
            "onsensor_bus": bus_stats,
            "modules": sorted([k for k, v in self.started.items() if v is not None]),
        }

    def vision_snapshot(self) -> Dict[str, Any]:
        proc = self._vlm_bridge()
        if proc is None:
            return {"available": False}
        modes = _safe_call(getattr(proc, "get_modes", None), default={}) or {}
        categories = _safe_call(getattr(proc, "get_mode_categories", None), default={}) or {}
        processing_mode = getattr(proc, "processing_mode", "unknown")
        follow_status = _safe_call(getattr(proc, "follow_status", None), default={}) or {}
        realtime = _safe_call(getattr(proc, "get_realtime_profile_status", None), default={}) or {}
        return {
            "available": True,
            "processing_mode": processing_mode,
            "modes": modes,
            "mode_categories": categories,
            "follow": follow_status,
            "realtime_profile": realtime,
            "remote_multimodal_enabled": bool(getattr(proc, "remote_mm_enabled", False)),
        }

    def people_snapshot(self, limit: int = 50) -> Dict[str, Any]:
        db = self._social_db()
        people: List[Dict[str, Any]] = []
        if db is not None and hasattr(db, "persons"):
            try:
                persons_repo = db.persons
                people_iter = []
                if hasattr(persons_repo, "list"):
                    people_iter = persons_repo.list(limit=limit) or []
                elif hasattr(persons_repo, "list_all"):
                    people_iter = persons_repo.list_all() or []
                for row in people_iter:
                    if isinstance(row, dict):
                        people.append(row)
                    elif hasattr(row, "__dict__"):
                        people.append({k: v for k, v in row.__dict__.items() if not k.startswith("_")})
            except Exception as exc:
                logger.debug("social_db.persons.list failed: %s", exc)
        if not people:
            proc = self._vlm_bridge()
            identity = getattr(proc, "person_identity", None) if proc is not None else None
            if identity is not None and hasattr(identity, "_records"):
                for rec in list(getattr(identity, "_records", {}).values())[:limit]:
                    people.append({
                        "person_id": getattr(rec, "person_id", ""),
                        "name": getattr(rec, "name", ""),
                        "recognition_level": getattr(rec, "recognition_level", 0),
                        "relationship": getattr(rec, "relationship", "unknown"),
                        "seen_count": getattr(rec, "seen_count", 0),
                        "last_seen": getattr(rec, "last_seen", None),
                    })
        return {"count": len(people), "people": people}

    def profiles_snapshot(self) -> Dict[str, Any]:
        agent = self._agent()
        profiles: List[str] = []
        active = "unknown"
        max_subagents = None
        if agent is not None:
            rt_cfg = getattr(agent, "config", {}).get("realtime_profile", {}) if isinstance(getattr(agent, "config", {}), dict) else {}
            active = str(rt_cfg.get("active", "unknown"))
            inner = rt_cfg.get("profiles", {})
            if isinstance(inner, dict):
                profiles = sorted(inner.keys())
            router = getattr(agent, "router", None)
            if router is not None:
                max_subagents = getattr(router, "max_subagents", None)
        return {
            "active": active,
            "profiles": profiles,
            "max_subagents": max_subagents,
        }

    def config_snapshot(self) -> Dict[str, Any]:
        reg = self._runtime_registry()
        if reg is None:
            return {"available": False, "keys": []}
        keys: List[Dict[str, Any]] = []
        try:
            if hasattr(reg, "list_keys"):
                for entry in reg.list_keys() or []:
                    keys.append(entry if isinstance(entry, dict) else {"key": str(entry)})
            elif hasattr(reg, "describe"):
                keys = list(reg.describe() or [])
        except Exception as exc:
            logger.debug("runtime registry list failed: %s", exc)
        return {"available": True, "keys": keys}

    def hardware_snapshot(self) -> Dict[str, Any]:
        arduino = self.started.get("arduino")
        esp = self.started.get("esp_link")
        camera = self.started.get("camera")
        neopixel = self.started.get("neopixel")
        return {
            "arduino": bool(arduino is not None),
            "esp_link": bool(esp is not None),
            "camera": bool(camera is not None),
            "neopixel": bool(neopixel is not None),
            "imx500": _safe_call(getattr(self._imx500_runner(), "available", None), default=False) if self._imx500_runner() is not None else False,
        }

    def     logs_snapshot(self, limit: int = 50) -> Dict[str, Any]:
        return {
            "ok": True,
            "url": "/logs/?n=50",
            "limit": int(limit),
        }

    def all_snapshots(self) -> Dict[str, Any]:
        return {
            "status": self.status_snapshot(),
            "vision": self.vision_snapshot(),
            "people": self.people_snapshot(),
            "profiles": self.profiles_snapshot(),
            "config": self.config_snapshot(),
            "hardware": self.hardware_snapshot(),
        }
