
from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

def _float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default

class TopomapMotionExecutor:
    DEFAULTS = {"enabled": True, "map_path": "data/topomap_places.json", "allow_base_motion": False, "require_ultrasonic_clearance": True, "min_clearance_cm": 28.0, "max_steps": 8, "max_step_duration_s": 2.0, "max_drive_value": 120}
    def __init__(self, cfg: Optional[Dict[str, Any]] = None, client: Any = None) -> None:
        self.cfg = dict(self.DEFAULTS)
        if isinstance(cfg, dict):
            self.cfg.update(cfg)
        self.client = client
        self.map_path = Path(str(self.cfg.get("map_path") or self.DEFAULTS["map_path"]))
        if not self.map_path.is_absolute():
            self.map_path = Path.cwd() / self.map_path
        self.map_path.parent.mkdir(parents=True, exist_ok=True)
        self._last: Dict[str, Any] = {"ok": True, "reason": "never_executed"}
        self._ensure_map()
    def _ensure_map(self) -> None:
        if not self.map_path.exists():
            self.map_path.write_text(json.dumps({"places": [], "edges": [], "updated_ts": time.time()}, ensure_ascii=False, indent=2), encoding="utf-8")
    def _load(self) -> Dict[str, Any]:
        self._ensure_map()
        try:
            data = json.loads(self.map_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {"places": [], "edges": []}
        except Exception:
            return {"places": [], "edges": []}
    def _save(self, data: Dict[str, Any]) -> None:
        data["updated_ts"] = time.time()
        self.map_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    def status(self) -> Dict[str, Any]:
        data = self._load()
        places = data.get("places") if isinstance(data.get("places"), list) else []
        edges = data.get("edges") if isinstance(data.get("edges"), list) else []
        return {"ok": True, "available": True, "config": dict(self.cfg), "map_path": str(self.map_path), "place_count": len(places), "edge_count": len(edges), "last": dict(self._last)}
    def list_map(self) -> Dict[str, Any]:
        return {"ok": True, "available": True, "map": self._load(), "status": self.status()}
    def learn_place(self, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        body = payload if isinstance(payload, dict) else {}
        place_id = str(body.get("id") or body.get("name") or f"place_{int(time.time())}").strip()
        place = {"id": place_id, "name": str(body.get("name") or place_id), "kind": str(body.get("kind") or "place"), "summary": str(body.get("summary") or "learned topomap place"), "safety_score": max(0.0, min(1.0, _float(body.get("safety_score"), 0.6))), "motion_plan": body.get("motion_plan") if isinstance(body.get("motion_plan"), list) else [], "created_ts": time.time(), "last_seen": time.time(), "details": body.get("details") if isinstance(body.get("details"), dict) else {}}
        data = self._load()
        places = [p for p in data.get("places", []) if isinstance(p, dict) and p.get("id") != place_id]
        places.append(place); data["places"] = places; self._save(data)
        return {"ok": True, "available": True, "place": place}
    def _find(self, place_id: str) -> Dict[str, Any]:
        for p in self._load().get("places", []):
            if isinstance(p, dict) and str(p.get("id") or p.get("name")) == str(place_id):
                return p
        return {}
    def execute_goal(self, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        body = payload if isinstance(payload, dict) else {}
        place_id = str(body.get("place_id") or body.get("id") or body.get("name") or "").strip()
        place = self._find(place_id) if place_id else {}
        if not place:
            self._last = {"ok": False, "available": True, "reason": "place_not_found", "place_id": place_id}; return dict(self._last)
        allow = bool(body.get("allow_base_motion", self.cfg.get("allow_base_motion", False)))
        if not allow:
            self._last = {"ok": True, "available": True, "moved": False, "pose_only": True, "reason": "base_motion_disabled", "place": place}; return dict(self._last)
        clearance = self._clearance_ok()
        if not clearance.get("ok"):
            self._last = {"ok": False, "available": True, "moved": False, "reason": "clearance_blocked", "clearance": clearance, "place": place}; return dict(self._last)
        plan = place.get("motion_plan") if isinstance(place.get("motion_plan"), list) else []
        if not plan:
            self._last = {"ok": False, "available": True, "moved": False, "reason": "motion_plan_missing", "place": place}; return dict(self._last)
        actions = [self._execute_step(s) for s in plan[: int(self.cfg.get("max_steps", 8))] if isinstance(s, dict)]
        moved = bool(actions and all(a.get("ok") is not False for a in actions))
        self._last = {"ok": moved, "available": True, "moved": moved, "reason": "executed" if moved else "step_failed", "place": place, "actions": actions}
        return dict(self._last)
    def _clearance_ok(self) -> Dict[str, Any]:
        if not self.cfg.get("require_ultrasonic_clearance", True):
            return {"ok": True, "reason": "not_required"}
        if self.client is None:
            return {"ok": False, "reason": "client_missing"}
        try:
            resp = self.client.read_sensor("ultra_read")
            dist = None
            if isinstance(resp, dict):
                for k in ("cm", "distance_cm", "distance", "value"):
                    if k in resp:
                        dist = _float(resp.get(k), -1.0); break
            if dist is None or dist < 0:
                return {"ok": False, "reason": "ultrasonic_unavailable", "response": resp}
            return {"ok": dist >= _float(self.cfg.get("min_clearance_cm"), 28.0), "distance_cm": dist, "min_clearance_cm": _float(self.cfg.get("min_clearance_cm"), 28.0)}
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}
    def _execute_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        if self.client is None:
            return {"ok": False, "reason": "client_missing", "step": step}
        kind = str(step.get("type") or step.get("cmd") or "").strip().lower()
        try:
            if kind in {"drive", "move"}:
                maxv = int(self.cfg.get("max_drive_value", 120)); value = max(-maxv, min(maxv, int(_float(step.get("value"), 0))))
                resp = self.client._arduino_request({"cmd": "drive", "value": value}, timeout=min(_float(step.get("duration_s"), 0.2), _float(self.cfg.get("max_step_duration_s"), 2.0)) + 0.5)
                return {"ok": bool(isinstance(resp, dict) and resp.get("ok")), "type": kind, "value": value, "response": resp}
            if kind in {"stepper", "turn"}:
                resp = self.client.set_stepper(int(step.get("id", 0)), str(step.get("mode") or "rel"), int(_float(step.get("value"), 0)), drive=int(step.get("drive", 160)))
                return {"ok": bool(isinstance(resp, dict) and resp.get("ok")), "type": kind, "response": resp}
            if kind in {"wait", "pause"}:
                time.sleep(max(0.0, min(_float(step.get("duration_s"), 0.2), _float(self.cfg.get("max_step_duration_s"), 2.0))))
                return {"ok": True, "type": kind}
            if kind == "home":
                resp = self.client.robot_command("home"); return {"ok": bool(isinstance(resp, dict) and resp.get("ok")), "type": kind, "response": resp}
            return {"ok": False, "reason": "unknown_step", "step": step}
        except Exception as exc:
            return {"ok": False, "reason": str(exc), "step": step}

__all__ = ["TopomapMotionExecutor"]
