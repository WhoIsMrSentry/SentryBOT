from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class OledAction:
    mode: str  # bitmap | animation | logo
    name: str


class FaceMapper:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.catalog_bitmaps: List[str] = [
            "alert", "angry", "blink_down", "blink_up", "blink", "bored", "despair", "disoriented",
            "excited", "focused", "furious", "happy", "look_down", "look_left", "look_right", "look_up",
            "normal", "sad", "scared", "sleepy", "surprised", "wink_left", "wink_right", "worried",
            "battery_full", "battery_low", "battery", "left_signal", "logo", "mode", "right_signal", "warning",
        ]
        self.catalog_animations: List[str] = [
            "wink", "blink", "scan", "sleep", "alert", "emotive", "icons", "all",
        ]

        self.state_map = dict(cfg.get("state_map", {}))
        self.event_map = dict(cfg.get("event_map", {}))
        self.arduino_event_map = dict(cfg.get("arduino_event_map", {}))
        self.fallback_unknown = str(cfg.get("fallback_unknown", "alert"))
        self.idle_bitmap = str(cfg.get("idle_bitmap", "normal"))

    def from_operational(self, operational: str) -> OledAction:
        key = str(operational or "").strip().lower()
        mapped = self.state_map.get(key)
        if isinstance(mapped, dict):
            return OledAction(mode=str(mapped.get("mode", "bitmap")), name=str(mapped.get("name", self.idle_bitmap)))
        if isinstance(mapped, str):
            return OledAction(mode="bitmap", name=mapped)
        return OledAction(mode="bitmap", name=self._hash_to_bitmap(key or self.idle_bitmap))

    def from_emotions(self, emotions: List[str]) -> OledAction:
        if not emotions:
            return OledAction(mode="bitmap", name=self.idle_bitmap)
        key = str(emotions[0]).strip().lower()
        mapped = self.event_map.get(f"emotion:{key}")
        if isinstance(mapped, dict):
            return OledAction(mode=str(mapped.get("mode", "bitmap")), name=str(mapped.get("name", self.fallback_unknown)))
        return OledAction(mode="bitmap", name=self._hash_to_bitmap(key))

    def from_interaction_event(self, event_type: str) -> OledAction:
        key = str(event_type or "").strip().lower()
        mapped = self.event_map.get(key)
        if isinstance(mapped, dict):
            return OledAction(mode=str(mapped.get("mode", "bitmap")), name=str(mapped.get("name", self.fallback_unknown)))
        return OledAction(mode="bitmap", name=self._hash_to_bitmap(key))

    def from_arduino_event(self, event_type: str) -> Optional[OledAction]:
        key = str(event_type or "").strip().lower()
        mapped = self.arduino_event_map.get(key)
        if isinstance(mapped, dict):
            return OledAction(mode=str(mapped.get("mode", "bitmap")), name=str(mapped.get("name", self.fallback_unknown)))
        return None

    def _hash_to_bitmap(self, key: str) -> str:
        if not key:
            return self.fallback_unknown
        idx = sum(ord(c) for c in key) % len(self.catalog_bitmaps)
        return self.catalog_bitmaps[idx]
