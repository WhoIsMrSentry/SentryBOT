from __future__ import annotations

from typing import Any, Dict, List, Optional


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _clean(value: Any, default: str = "") -> str:
    text = str(value if value is not None else default).strip()
    return " ".join(text.split())


def _confidence(value: Any, default: float = 0.6) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        out = default
    return max(0.0, min(1.0, out))


class WorldMemoryAutoWriter:
    DEFAULTS: Dict[str, Any] = {
        "enabled": True,
        "write_people": True,
        "write_objects": True,
        "write_events": True,
        "write_observations": True,
        "write_low_salience_silence": True,
    }

    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        raw = cfg if isinstance(cfg, dict) else {}
        self.cfg: Dict[str, Any] = dict(self.DEFAULTS)
        self.cfg.update(raw)

    def enabled(self) -> bool:
        return bool(self.cfg.get("enabled", True))

    def from_vision(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.enabled():
            return []
        ctx = _as_dict(context)
        out: List[Dict[str, Any]] = []
        conf = _confidence(ctx.get("confidence"), 0.7)
        summary = _clean(ctx.get("summary") or ctx.get("reason") or "vision observation", "vision observation")
        reason = _clean(ctx.get("reason"), "vision.context")
        if bool(ctx.get("person_seen") or ctx.get("owner_present")) and self.cfg.get("write_people", True):
            name = _clean(ctx.get("person") or ctx.get("person_name") or "owner")
            out.append({"kind": "people", "name": name, "summary": "owner seen nearby" if name == "owner" else f"{name} seen nearby", "source": "vision", "confidence": conf, "salience": max(0.75, conf), "tags": ["owner"] if name == "owner" else ["person"], "properties": {"reason": reason, "owner_present": bool(ctx.get("owner_present", True))}})
        if bool(ctx.get("new_object")) and self.cfg.get("write_objects", True):
            objects = [_clean(x) for x in _as_list(ctx.get("objects")) if _clean(x)] or ["unknown object"]
            for obj in objects[:5]:
                out.append({"kind": "objects", "name": obj, "summary": summary or f"new object observed: {obj}", "source": "vision", "confidence": conf, "salience": max(0.80, conf), "tags": ["novel"], "properties": {"reason": reason, "new_object": True}})
        hazards = [_clean(x) for x in _as_list(ctx.get("hazards")) if _clean(x)]
        if hazards and self.cfg.get("write_events", True):
            out.append({"kind": "events", "name": "hazard", "summary": summary or ", ".join(hazards), "source": "vision", "confidence": conf, "salience": 0.95, "tags": ["safety", "hazard"], "properties": {"reason": reason, "hazards": hazards}})
        if self.cfg.get("write_observations", True):
            if bool(ctx.get("no_person")):
                out.append({"kind": "observations", "name": "no person visible", "summary": summary or "no person visible", "source": "vision", "confidence": conf, "salience": 0.45, "tags": ["no_person"], "properties": {"reason": reason}})
            elif bool(ctx.get("scene_stable")):
                out.append({"kind": "observations", "name": "stable quiet room", "summary": summary or "stable quiet room", "source": "vision", "confidence": conf, "salience": 0.35, "tags": ["stable"], "properties": {"reason": reason}})
        return out

    def from_audio(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.enabled():
            return []
        ctx = _as_dict(context)
        out: List[Dict[str, Any]] = []
        conf = _confidence(ctx.get("confidence"), 0.7)
        event_type = _clean(ctx.get("event_type"), "audio")
        transcript = _clean(ctx.get("transcript"), "")
        reason = _clean(ctx.get("reason"), f"audio.{event_type}")
        if bool(ctx.get("wakeword") or ctx.get("speech") or ctx.get("owner_present")) and self.cfg.get("write_people", True):
            out.append({"kind": "people", "name": "owner", "summary": "owner heard nearby", "source": "audio", "confidence": conf, "salience": max(0.78, conf), "tags": ["owner", "heard"], "properties": {"reason": reason, "wakeword": bool(ctx.get("wakeword")), "speech": bool(ctx.get("speech"))}})
        if bool(ctx.get("wakeword")) and self.cfg.get("write_events", True):
            out.append({"kind": "events", "name": "wakeword", "summary": "wakeword detected", "source": "audio", "confidence": conf, "salience": 0.86, "tags": ["wakeword", "owner_attention"], "properties": {"reason": reason}})
        if bool(ctx.get("speech")) and self.cfg.get("write_events", True):
            out.append({"kind": "events", "name": "speech", "summary": transcript or "speech detected", "source": "audio", "confidence": conf, "salience": 0.82, "tags": ["speech"], "properties": {"reason": reason, "transcript": transcript}})
        if bool(ctx.get("sound")) and self.cfg.get("write_events", True):
            out.append({"kind": "events", "name": "sound", "summary": "small sound detected", "source": "audio", "confidence": conf, "salience": 0.65, "tags": ["sound", "curiosity"], "properties": {"reason": reason}})
        if bool(ctx.get("loud")) and self.cfg.get("write_events", True):
            out.append({"kind": "events", "name": "loud noise", "summary": "loud noise detected", "source": "audio", "confidence": conf, "salience": 0.94, "tags": ["safety", "loud"], "properties": {"reason": reason}})
        if bool(ctx.get("silence")) and self.cfg.get("write_low_salience_silence", True):
            out.append({"kind": "observations", "name": "long quiet period", "summary": "long quiet period", "source": "audio", "confidence": conf, "salience": 0.30, "tags": ["silence"], "properties": {"reason": reason}})
        return out

    def build(self, source_type: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        st = _clean(source_type).lower().replace("-", "_")
        if st in {"vision", "vision_context", "camera"}:
            return self.from_vision(context)
        if st in {"audio", "audio_context", "sound"}:
            return self.from_audio(context)
        return []
