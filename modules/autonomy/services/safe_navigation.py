from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class SafeNavigationMemory:
    """Safe-place selector and pose-only rest executor.

    Base movement is disabled by default. A learned map can enable base motion
    explicitly; otherwise the robot chooses a rest place semantically and applies
    the safe rest pose, dim expression and lights-off state.
    """

    DEFAULTS: Dict[str, Any] = {
        "enabled": True,
        "places_path": "data/safe_places.json",
        "allow_base_motion": False,
        "default_rest_place": "quiet_corner",
        "rest_pose": {"pan": 90, "tilt": 125},
    }

    def __init__(self, cfg: Optional[Dict[str, Any]] = None, client: Any = None) -> None:
        raw = cfg if isinstance(cfg, dict) else {}
        self.cfg = dict(self.DEFAULTS)
        self.cfg.update(raw)
        self.client = client
        self.path = Path(str(self.cfg.get("places_path") or self.DEFAULTS["places_path"]))
        if not self.path.is_absolute():
            self.path = Path.cwd() / self.path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last: Dict[str, Any] = {"ok": True, "available": False, "reason": "never_executed"}
        self._ensure_defaults()

    def _ensure_defaults(self) -> None:
        if self.path.exists():
            return
        data = {
            "places": [
                {
                    "id": "quiet_corner",
                    "kind": "rest_place",
                    "name": "quiet_corner",
                    "summary": "Default quiet rest place. Base motion stays disabled until a real map confirms it.",
                    "safety_score": 0.55,
                    "learned": False,
                    "pose_only": True,
                    "created_ts": time.time(),
                }
            ]
        }
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {"places": []}
        except Exception:
            return {"places": []}

    def _save(self, data: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_places(self) -> Dict[str, Any]:
        data = self._load()
        places = data.get("places") if isinstance(data.get("places"), list) else []
        return {"ok": True, "available": True, "places": places, "count": len(places), "path": str(self.path)}

    def learn_place(self, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        body = payload if isinstance(payload, dict) else {}
        place_id = str(body.get("id") or body.get("name") or f"place_{int(time.time())}").strip()
        place = {
            "id": place_id,
            "kind": str(body.get("kind") or "rest_place"),
            "name": str(body.get("name") or place_id),
            "summary": str(body.get("summary") or "learned safe place"),
            "safety_score": max(0.0, min(1.0, _safe_float(body.get("safety_score"), 0.6))),
            "learned": True,
            "pose_only": bool(body.get("pose_only", not bool(self.cfg.get("allow_base_motion", False)))),
            "created_ts": float(body.get("created_ts") or time.time()),
            "last_seen": float(body.get("last_seen") or time.time()),
            "details": body.get("details") if isinstance(body.get("details"), dict) else {},
        }
        data = self._load()
        places = [p for p in data.get("places", []) if isinstance(p, dict) and p.get("id") != place_id]
        places.append(place)
        data["places"] = places
        self._save(data)
        return {"ok": True, "available": True, "place": place}

    def select_rest_place(self) -> Dict[str, Any]:
        places = [p for p in self._load().get("places", []) if isinstance(p, dict)]
        candidates = [p for p in places if str(p.get("kind") or "") in {"rest_place", "safe_place", "corner"}]
        if not candidates:
            self._ensure_defaults()
            candidates = [p for p in self._load().get("places", []) if isinstance(p, dict)]
        candidates.sort(key=lambda p: (_safe_float(p.get("safety_score"), 0.0), _safe_float(p.get("last_seen") or p.get("created_ts"), 0.0)), reverse=True)
        place = candidates[0] if candidates else {}
        return {"ok": bool(place), "available": bool(place), "place": place, "allow_base_motion": bool(self.cfg.get("allow_base_motion", False))}

    def execute_rest_corner(self, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        body = payload if isinstance(payload, dict) else {}
        selected = self.select_rest_place()
        place = selected.get("place") if isinstance(selected.get("place"), dict) else {}
        allow_motion = bool(body.get("allow_base_motion", self.cfg.get("allow_base_motion", False)))
        actions: List[Dict[str, Any]] = []
        nav_result = None
        if allow_motion and self.client is not None and not bool(place.get("pose_only", False)):
            try:
                nav_result = self.client.queue_action("navigation.goal", priority=60, ttl_ms=20000, payload={"place": place})
                actions.append({"type": "navigation.goal", "result": nav_result})
            except Exception as exc:
                actions.append({"type": "navigation.goal", "ok": False, "error": str(exc)})
        else:
            actions.append({"type": "navigation.skipped", "reason": "base_motion_disabled_or_pose_only"})
        if self.client is not None:
            pose = self.cfg.get("rest_pose") if isinstance(self.cfg.get("rest_pose"), dict) else {}
            pan = int(pose.get("pan", 90))
            tilt = int(pose.get("tilt", 125))
            try:
                actions.append({"type": "expression", "result": self.client.set_expression_event("navigation.resting", {"place": place})})
            except Exception as exc:
                actions.append({"type": "expression", "ok": False, "error": str(exc)})
            try:
                actions.append({"type": "head", "result": self.client.move_head(pan, tilt)})
            except Exception as exc:
                actions.append({"type": "head", "ok": False, "error": str(exc)})
            try:
                actions.append({"type": "liveliness", "result": self.client.set_liveliness(False)})
            except Exception as exc:
                actions.append({"type": "liveliness", "ok": False, "error": str(exc)})
            try:
                actions.append({"type": "lights", "result": self.client.set_neopixel("SOLID", color=[0, 0, 0], duration=2.0)})
            except Exception as exc:
                actions.append({"type": "lights", "ok": False, "error": str(exc)})
        out = {
            "ok": True,
            "available": True,
            "timestamp": time.time(),
            "place": place,
            "base_motion_requested": bool(nav_result),
            "pose_only": not bool(nav_result),
            "actions": actions,
            "reason": "rest_corner_pose_applied" if not nav_result else "rest_corner_navigation_requested",
        }
        self._last = dict(out)
        return out

    def status(self) -> Dict[str, Any]:
        return {"ok": True, "enabled": bool(self.cfg.get("enabled", True)), "config": dict(self.cfg), "last": dict(self._last), "places": self.list_places()}


__all__ = ["SafeNavigationMemory"]
