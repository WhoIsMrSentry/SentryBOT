
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled", "seen", "present"}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


class VisionContextNeedsBridge:
    DEFAULTS: Dict[str, Any] = {
        "enabled": True,
        "ttl_s": 45.0,
        "owner_seen_timeout_s": 60.0,
        "history_limit": 20,
        "novelty_curiosity": 92.0,
        "no_person_stimulation": 62.0,
        "stable_curiosity": 35.0,
    }

    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        raw = cfg if isinstance(cfg, dict) else {}
        self.cfg: Dict[str, Any] = dict(self.DEFAULTS)
        self.cfg.update(raw)
        self._latest: Dict[str, Any] = {
            "ok": True,
            "available": False,
            "reason": "no_vision_context_yet",
            "timestamp": 0.0,
        }
        self._owner_last_seen_ts: float = 0.0
        self._history: List[Dict[str, Any]] = []

    def observe(self, payload: Optional[Dict[str, Any]], *, source: str = "manual", now: Optional[float] = None) -> Dict[str, Any]:
        ts = float(now if now is not None else time.time())
        data = _as_dict(payload)
        summary = str(data.get("summary") or data.get("caption") or data.get("scene") or "").strip()
        objects = _as_list(data.get("objects") or data.get("detected_objects"))
        hazards = _as_list(data.get("hazards") or data.get("hazard"))
        person_seen = _as_bool(data.get("person_seen"), False) or _as_bool(data.get("person_present"), False) or _as_bool(data.get("owner_present"), False)
        owner_present = _as_bool(data.get("owner_present"), person_seen)
        no_person = _as_bool(data.get("no_person"), False) or ("person_seen" in data and not _as_bool(data.get("person_seen"), False))
        new_object = _as_bool(data.get("new_object"), False) or _as_bool(data.get("novelty"), False) or _as_bool(data.get("unknown_object"), False)
        scene_stable = _as_bool(data.get("scene_stable"), False) or _as_bool(data.get("stable"), False)
        confidence = max(0.0, min(1.0, _as_float(data.get("confidence"), 0.65)))
        if person_seen or owner_present:
            self._owner_last_seen_ts = ts
        context = {
            "ok": True,
            "available": True,
            "timestamp": ts,
            "source": str(source or data.get("source") or "manual"),
            "summary": summary,
            "objects": objects,
            "hazards": hazards,
            "person_seen": bool(person_seen),
            "owner_present": bool(owner_present),
            "no_person": bool(no_person and not person_seen and not owner_present),
            "new_object": bool(new_object),
            "scene_stable": bool(scene_stable),
            "confidence": round(confidence, 2),
            "reason": self._reason_for(person_seen=person_seen, owner_present=owner_present, no_person=no_person, new_object=new_object, scene_stable=scene_stable, hazards=hazards),
        }
        self._latest = context
        self._push_history(context)
        return self.status(now=ts)

    def status(self, *, now: Optional[float] = None) -> Dict[str, Any]:
        ts = float(now if now is not None else time.time())
        latest = dict(self._latest)
        age = max(0.0, ts - _as_float(latest.get("timestamp"), 0.0)) if latest.get("available") else 0.0
        ttl = max(1.0, _as_float(self.cfg.get("ttl_s"), 45.0))
        latest["enabled"] = _as_bool(self.cfg.get("enabled"), True)
        latest["age_s"] = round(age, 1)
        latest["fresh"] = bool(latest.get("available") and age <= ttl)
        latest["owner_last_seen_ts"] = self._owner_last_seen_ts
        latest["history"] = list(self._history[-10:])
        return latest

    def context(self, *, now: Optional[float] = None) -> Dict[str, Any]:
        ts = float(now if now is not None else time.time())
        if not _as_bool(self.cfg.get("enabled"), True):
            return {"available": False, "reason": "vision_context_bridge_disabled"}
        st = self.status(now=ts)
        if not st.get("available") or not st.get("fresh"):
            return {"available": False, "reason": st.get("reason") or "vision_context_stale", "status": st}
        scene: Dict[str, Any] = {
            "summary": st.get("summary", ""),
            "objects": list(st.get("objects") or []),
            "hazards": list(st.get("hazards") or []),
            "person_seen": bool(st.get("person_seen")),
            "owner_present": bool(st.get("owner_present")),
            "no_person": bool(st.get("no_person")),
            "new_object": bool(st.get("new_object")),
            "novelty": bool(st.get("new_object")),
            "scene_stable": bool(st.get("scene_stable")),
            "vision_confidence": st.get("confidence", 0.0),
        }
        mood_overrides: Dict[str, Any] = {}
        needs_overrides: Dict[str, Any] = {}
        if scene.get("new_object"):
            mood_overrides["curiosity"] = max(_as_float(mood_overrides.get("curiosity"), 0.0), _as_float(self.cfg.get("novelty_curiosity"), 92.0))
            needs_overrides["stimulation"] = max(_as_float(needs_overrides.get("stimulation"), 0.0), 85.0)
        if scene.get("no_person"):
            needs_overrides["stimulation"] = max(_as_float(needs_overrides.get("stimulation"), 0.0), _as_float(self.cfg.get("no_person_stimulation"), 62.0))
        if scene.get("scene_stable") and not scene.get("new_object") and not scene.get("hazards"):
            mood_overrides["curiosity"] = min(_as_float(self.cfg.get("stable_curiosity"), 35.0), _as_float(self.cfg.get("stable_curiosity"), 35.0))
        owner_timeout = max(1.0, _as_float(self.cfg.get("owner_seen_timeout_s"), 60.0))
        owner_recent = self._owner_last_seen_ts > 0.0 and (ts - self._owner_last_seen_ts) <= owner_timeout
        return {
            "available": True,
            "status": st,
            "scene": scene,
            "mood_overrides": mood_overrides,
            "needs_overrides": needs_overrides,
            "owner_present": bool(scene.get("owner_present") or owner_recent),
            "owner_last_seen_ts": self._owner_last_seen_ts or None,
        }

    def _push_history(self, item: Dict[str, Any]) -> None:
        compact = {
            "timestamp": item.get("timestamp"),
            "reason": item.get("reason"),
            "summary": item.get("summary", ""),
            "owner_present": item.get("owner_present", False),
            "no_person": item.get("no_person", False),
            "new_object": item.get("new_object", False),
            "hazards": item.get("hazards", []),
        }
        self._history.append(compact)
        limit = int(_as_float(self.cfg.get("history_limit"), 20))
        self._history = self._history[-max(1, limit):]

    def _reason_for(self, *, person_seen: bool, owner_present: bool, no_person: bool, new_object: bool, scene_stable: bool, hazards: List[Any]) -> str:
        if hazards:
            return "vision.hazard"
        if owner_present or person_seen:
            return "vision.person_seen"
        if new_object:
            return "vision.new_object"
        if no_person:
            return "vision.no_person"
        if scene_stable:
            return "vision.scene_stable"
        return "vision.context"
