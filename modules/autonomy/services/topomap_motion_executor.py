
from __future__ import annotations

import random
import threading
import time
from typing import Any, Dict, List, Optional

from modules.arduino_serial.contract import build_drive_cmd
from .storage_utils import atomic_write_json, read_json_dict, resolve_autonomy_path

def _float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _extract_motion_steps(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the first non-empty step list across supported plan keys."""
    for key in ("motion_plan", "steps", "plan", "actions"):
        raw = source.get(key)
        if isinstance(raw, list) and raw:
            return [dict(item) if isinstance(item, dict) else item for item in raw]
    return []


class TopomapMotionExecutor:
    DEFAULTS = {"enabled": True, "map_path": "data/topomap_places.json", "allow_base_motion": False, "require_ultrasonic_clearance": True, "min_clearance_cm": 28.0, "max_steps": 8, "max_step_duration_s": 2.0, "max_drive_value": 120}
    def __init__(self, cfg: Optional[Dict[str, Any]] = None, client: Any = None) -> None:
        self.cfg = dict(self.DEFAULTS)
        if isinstance(cfg, dict):
            self.cfg.update(cfg)
        self.client = client
        self._lock = threading.RLock()
        self.map_path = resolve_autonomy_path(self.cfg.get("map_path"), str(self.DEFAULTS["map_path"]))
        self.map_path.parent.mkdir(parents=True, exist_ok=True)
        self._last: Dict[str, Any] = {"ok": True, "reason": "never_executed"}
        self._ensure_map()
    def _ensure_map(self) -> None:
        with self._lock:
            if not self.map_path.exists():
                atomic_write_json(self.map_path, {"places": [], "edges": [], "updated_ts": time.time()}, lock=self._lock)
    def _load(self) -> Dict[str, Any]:
        with self._lock:
            self._ensure_map()
            return read_json_dict(self.map_path, lambda: {"places": [], "edges": []}, lock=self._lock)
    def _save(self, data: Dict[str, Any]) -> None:
        with self._lock:
            data["updated_ts"] = time.time()
            atomic_write_json(self.map_path, data, lock=self._lock)
    def status(self) -> Dict[str, Any]:
        data = self._load()
        places = data.get("places") if isinstance(data.get("places"), list) else []
        edges = data.get("edges") if isinstance(data.get("edges"), list) else []
        return {"ok": True, "available": True, "config": dict(self.cfg), "map_path": str(self.map_path), "place_count": len(places), "edge_count": len(edges), "last": dict(self._last)}
    def list_map(self) -> Dict[str, Any]:
        return {"ok": True, "available": True, "map": self._load(), "status": self.status()}
    def learn_place(self, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Topomap place tags are normalized before persistence.
        payload = dict(payload or {})
        validation = self.cfg.get("place_validation", {})
        validation = validation if isinstance(validation, dict) else {}
        raw_tags = payload.get("tags", [])
        raw_tags = raw_tags.split(",") if isinstance(raw_tags, str) else raw_tags
        tags = sorted({str(tag).strip() for tag in raw_tags if str(tag).strip()}) if isinstance(raw_tags, (list, tuple, set)) else []
        allowed_tags = {str(tag).strip() for tag in validation.get("allowed_tags", []) if str(tag).strip()}
        if allowed_tags and not set(tags).issubset(allowed_tags):
            return {"ok": False, "reason": "unsupported_place_tag", "tags": tags}
        safe_required_for = {str(tag).strip() for tag in validation.get("safe_required_for", []) if str(tag).strip()}
        if set(tags).intersection(safe_required_for) and "safe" not in tags:
            return {"ok": False, "reason": "safe_tag_required", "tags": tags}
        distance_required_for = {str(tag).strip() for tag in validation.get("distance_required_for", []) if str(tag).strip()}
        if set(tags).intersection(distance_required_for) and _float(payload.get("distance_from_owner_m"), -1.0) < 0.0:
            return {"ok": False, "reason": "owner_distance_required", "tags": tags}
        motion_required_for = {str(tag).strip() for tag in validation.get("motion_required_for", []) if str(tag).strip()}
        has_motion = any(isinstance(payload.get(key), list) and payload.get(key) for key in ("steps", "plan", "actions"))
        if set(tags).intersection(motion_required_for) and not has_motion:
            return {"ok": False, "reason": "motion_plan_required", "tags": tags}
        payload["tags"] = tags
        body = payload if isinstance(payload, dict) else {}
        place_id = str(body.get("id") or body.get("name") or f"place_{int(time.time())}").strip()
        steps = _extract_motion_steps(body)
        place: Dict[str, Any] = {
            "id": place_id,
            "name": str(body.get("name") or place_id),
            "kind": str(body.get("kind") or "place"),
            "summary": str(body.get("summary") or "learned topomap place"),
            "safety_score": max(0.0, min(1.0, _float(body.get("safety_score"), 0.6))),
            "tags": tags,
            "motion_plan": steps,
            "steps": list(steps),
            "pose_only": bool(body.get("pose_only", not bool(self.cfg.get("allow_base_motion", False)))),
            "created_ts": float(body.get("created_ts") or time.time()),
            "last_seen": float(body.get("last_seen") or time.time()),
            "details": body.get("details") if isinstance(body.get("details"), dict) else {},
        }
        if "distance_from_owner_m" in body and body.get("distance_from_owner_m") is not None:
            dist = _float(body.get("distance_from_owner_m"), -1.0)
            if dist >= 0.0:
                place["distance_from_owner_m"] = dist
        with self._lock:
            data = self._load()
            places = [p for p in data.get("places", []) if isinstance(p, dict) and p.get("id") != place_id]
            places.append(place)
            data["places"] = places
            self._save(data)
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
        inline_steps = _extract_motion_steps(body)
        if not place and inline_steps:
            place = {"id": place_id or "inline_goal", "name": str(body.get("name") or place_id or "inline_goal"), "motion_plan": inline_steps}
        if not place:
            self._last = {"ok": False, "available": True, "reason": "place_not_found", "place_id": place_id}; return dict(self._last)
        allow = bool(body.get("allow_base_motion", self.cfg.get("allow_base_motion", False)))
        if not allow:
            self._last = {"ok": True, "available": True, "moved": False, "pose_only": True, "reason": "base_motion_disabled", "place": place}; return dict(self._last)
        clearance = self._clearance_ok()
        if not clearance.get("ok"):
            self._last = {"ok": False, "available": True, "moved": False, "reason": "clearance_blocked", "clearance": clearance, "place": place}; return dict(self._last)
        plan = inline_steps or _extract_motion_steps(place)
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
                resp = self.client._arduino_request(
                    build_drive_cmd(value),
                    timeout=min(_float(step.get("duration_s"), 0.2), _float(self.cfg.get("max_step_duration_s"), 2.0)) + 0.5,
                )
                return {"ok": bool(isinstance(resp, dict) and resp.get("ok")), "type": kind, "value": value, "response": resp}
            if kind in {"stepper", "turn"}:
                raw_mode = str(step.get("mode") or "pos").strip().lower()
                mode = raw_mode if raw_mode in {"pos", "vel"} else "pos"
                resp = self.client.set_stepper(int(step.get("id", 0)), mode, int(_float(step.get("value"), 0)), drive=int(step.get("drive", 160)))
                return {"ok": bool(isinstance(resp, dict) and resp.get("ok")), "type": kind, "response": resp}
            if kind in {"wait", "pause"}:
                time.sleep(max(0.0, min(_float(step.get("duration_s"), 0.2), _float(self.cfg.get("max_step_duration_s"), 2.0))))
                return {"ok": True, "type": kind}
            if kind == "home":
                resp = self.client.robot_command("home"); return {"ok": bool(isinstance(resp, dict) and resp.get("ok")), "type": kind, "response": resp}
            return {"ok": False, "reason": "unknown_step", "step": step}
        except Exception as exc:
            return {"ok": False, "reason": str(exc), "step": step}

    def execute_companion_policy(self, policy_name: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        policies = self.cfg.get("companion_policies", {})
        policies = policies if isinstance(policies, dict) else {}
        policy = policies.get(str(policy_name or ""), {})
        policy = policy if isinstance(policy, dict) else {}
        if not bool(policy.get("enabled", False)):
            return {"ok": False, "reason": "companion_policy_disabled", "policy": policy_name}
        required_tags = {str(tag).strip() for tag in policy.get("required_tags", []) if str(tag).strip()}
        minimum_distance = _float(policy.get("minimum_distance_from_owner_m"), 0.0)
        places = self._load().get("places", [])
        candidates = []
        for place in places if isinstance(places, list) else []:
            if not isinstance(place, dict):
                continue
            tags = {str(tag).strip() for tag in place.get("tags", []) if str(tag).strip()}
            if not required_tags.issubset(tags):
                continue
            distance = _float(place.get("distance_from_owner_m"), -1.0)
            if minimum_distance > 0.0 and distance < minimum_distance:
                continue
            steps = _extract_motion_steps(place)
            if not steps:
                continue
            candidates.append(place)
        if not candidates:
            return {"ok": False, "reason": "no_safe_topomap_candidate", "policy": policy_name}
        max_attempts = max(1, int(policy.get("max_attempts", 1) or 1))
        remaining = list(candidates)
        attempts = []
        last_result: Dict[str, Any] = {"ok": False, "reason": "no_safe_topomap_candidate"}
        while remaining and len(attempts) < max_attempts:
            selected = random.choice(remaining) if str(policy.get("selection") or "").lower() == "random" else remaining[0]
            remaining.remove(selected)
            selected_steps = _extract_motion_steps(selected)
            result = self.execute_goal({
                "place_id": str(selected.get("id") or selected.get("name") or ""),
                "name": str(selected.get("name") or ""),
                "steps": selected_steps,
            })
            result["policy"] = policy_name
            result["selected_place"] = str(selected.get("name") or "")
            attempts.append({"place": result["selected_place"], "ok": bool(result.get("ok")), "reason": result.get("reason")})
            if result.get("ok"):
                result["recovery"] = {"attempts": attempts, "fallback_behavior": None}
                return result
            last_result = result
        last_result["policy"] = policy_name
        last_result["recovery"] = {
            "attempts": attempts,
            "fallback_behavior": str(policy.get("fallback_behavior") or ""),
        }
        return last_result

__all__ = ["TopomapMotionExecutor"]
