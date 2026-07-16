from __future__ import annotations
OLED_FACE_MAPPER_COMPATIBILITY_CONTRACT = True
OLED_FACE_MAPPER_ROLE = "face_state_event_alias_mapper"


from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    from modules.common.emotion_vocab import get_vocab as _get_emotion_vocab
except Exception:  # pragma: no cover
    _get_emotion_vocab = None

from .legacy_map import catalog_animations, catalog_moods, resolve_mood


@dataclass(frozen=True)
class OledAction:
    mode: str  # bitmap | animation | logo
    name: str


class FaceMapper:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.catalog_bitmaps: List[str] = list(catalog_moods())
        self.catalog_animations: List[str] = list(catalog_animations())

        self.state_map = dict(cfg.get("state_map", {}))
        self.event_map = dict(cfg.get("event_map", {}))
        self.arduino_event_map = dict(cfg.get("arduino_event_map", {}))
        self.fallback_unknown = resolve_mood(str(cfg.get("fallback_unknown", "neutral")))
        self.idle_bitmap = resolve_mood(str(cfg.get("idle_bitmap", "neutral")))

    def from_operational(self, operational: str) -> OledAction:
        key = str(operational or "").strip().lower()
        mapped = self.state_map.get(key)
        if isinstance(mapped, dict):
            return OledAction(mode=str(mapped.get("mode", "bitmap")), name=str(mapped.get("name", self.idle_bitmap)))
        if isinstance(mapped, str):
            return OledAction(mode="bitmap", name=mapped)
        return OledAction(mode="bitmap", name=self.idle_bitmap)

    def from_emotions(self, emotions: List[str]) -> OledAction:
        if not emotions:
            return OledAction(mode="bitmap", name=self.idle_bitmap)
        key = str(emotions[0]).strip().lower()
        mapped = self.event_map.get(f"emotion:{key}")
        if isinstance(mapped, dict):
            return OledAction(mode=str(mapped.get("mode", "bitmap")), name=str(mapped.get("name", self.fallback_unknown)))
        if _get_emotion_vocab is not None:
            try:
                render = _get_emotion_vocab().render(key)
                canon_override = self.event_map.get(f"emotion:{render.canonical}")
                if isinstance(canon_override, dict):
                    return OledAction(
                        mode=str(canon_override.get("mode", "bitmap")),
                        name=str(canon_override.get("name", render.oled)),
                    )
                return OledAction(mode="bitmap", name=resolve_mood(render.oled))
            except Exception:
                pass
        return OledAction(mode="bitmap", name=self.fallback_unknown)

    def from_interaction_event(self, event_type: str) -> OledAction:
        key = str(event_type or "").strip().lower()
        if key.startswith("emotion:"):
            label = key.split(":", 1)[1]
            return self.from_emotions([label])
        if key.startswith("gesture:"):
            name = key.split(":", 1)[1]
            return OledAction(mode="gesture", name=name)
        if key.startswith("activity:"):
            name = key.split(":", 1)[1]
            return OledAction(mode="animation", name=name)
        mapped = self.event_map.get(key)
        if isinstance(mapped, dict):
            return OledAction(mode=str(mapped.get("mode", "bitmap")), name=str(mapped.get("name", self.fallback_unknown)))
        return OledAction(mode="bitmap", name=self.fallback_unknown)

    def from_arduino_event(self, event_type: str) -> Optional[OledAction]:
        key = str(event_type or "").strip().lower()
        mapped = self.arduino_event_map.get(key)
        if isinstance(mapped, dict):
            return OledAction(mode=str(mapped.get("mode", "bitmap")), name=str(mapped.get("name", self.fallback_unknown)))
        return None
