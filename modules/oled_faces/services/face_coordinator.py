"""Resolve conflicts between interaction events, polled emotions, and operational state."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from .mapper import FaceMapper, OledAction


# Operational modes that should own the face until they change.
_DOMINANT_OPERATIONAL: Set[str] = {
    "listening", "thinking", "speaking", "sleeping", "alert",
}

# Modes where polled emotions may update the face.
_PASSIVE_OPERATIONAL: Set[str] = {
    "idle", "boot", "active", "maintenance",
    "charging", "charged", "low_battery",
}

_SESSION_START: Dict[str, str] = {
    "speech.start": "speaking",
    "wakeword.detected": "listening",
}

_SESSION_END: Set[str] = {"speech.end"}


@dataclass
class FaceDecision:
    action: OledAction
    priority: int
    source: str
    apply: bool = True


class FaceCoordinator:
    def __init__(self, mapper: FaceMapper, cfg: Dict[str, Any]):
        self.mapper = mapper
        self.cfg = cfg
        self._session_kind: Optional[str] = None
        self._session_until: float = 0.0
        self._last_resolved_mood: str = ""
        self._last_mood_apply_ts: float = 0.0

    def on_event(
        self,
        event_type: str,
        action: OledAction,
        priority: int,
        baseline: Optional[OledAction] = None,
    ) -> FaceDecision:
        key = str(event_type or "").strip().lower()
        now = time.time()

        if key in _SESSION_START:
            self._session_kind = _SESSION_START[key]
            self._session_until = now + float(self.cfg.get("session_hold_s", 45.0))
            return FaceDecision(action=action, priority=max(priority, 72), source="event")

        if key in _SESSION_END:
            self._session_kind = None
            self._session_until = now + float(self.cfg.get("animation_hold_s", 1.4))
            return FaceDecision(action=baseline or self._idle_action(), priority=68, source="event")

        if key.startswith("emotion:"):
            label = key.split(":", 1)[1]
            mood_action = self.mapper.from_emotions([label])
            if self._session_active(now) and self._session_kind == "speaking":
                return FaceDecision(action=mood_action, priority=priority, source="event", apply=False)
            if not self._emotion_stable(mood_action.name, now):
                return FaceDecision(action=mood_action, priority=priority, source="event", apply=False)
            return FaceDecision(action=mood_action, priority=max(priority, 62), source="event")

        if key in {"autonomy.blink", "autonomy.look_around", "autonomy.stretch"}:
            return FaceDecision(action=action, priority=min(priority, 45), source="event")

        return FaceDecision(action=action, priority=priority, source="event")

    def from_state(self, operational: str, emotions: List[str], *, op_changed: bool, emo_changed: bool) -> Optional[FaceDecision]:
        now = time.time()
        op = str(operational or "idle").strip().lower()

        if self._session_active(now):
            if op_changed and op in _DOMINANT_OPERATIONAL:
                mapped = self.mapper.from_operational(op)
                return FaceDecision(action=mapped, priority=58, source="state")
            return None

        if op_changed and op in _DOMINANT_OPERATIONAL:
            mapped = self.mapper.from_operational(op)
            return FaceDecision(action=mapped, priority=55, source="state")

        if emo_changed and emotions and (op in _PASSIVE_OPERATIONAL or op not in _DOMINANT_OPERATIONAL):
            mapped = self.mapper.from_emotions(emotions)
            if not self._emotion_stable(mapped.name, now):
                return None
            pri = 60
            return FaceDecision(action=mapped, priority=pri, source="emotion")

        if op_changed:
            mapped = self.mapper.from_operational(op)
            return FaceDecision(action=mapped, priority=50 if mapped.mode == "bitmap" else 52, source="state")

        return None

    def session_active(self) -> bool:
        return self._session_active(time.time())

    def should_clear_activity(self, now: float, hold_until: float) -> bool:
        if self._session_active(now):
            return False
        return now >= hold_until

    def note_applied_mood(self, mood_name: str) -> None:
        self._last_resolved_mood = str(mood_name or "").strip().lower()
        self._last_mood_apply_ts = time.time()

    def _session_active(self, now: float) -> bool:
        return bool(self._session_kind) and now < self._session_until

    def _emotion_stable(self, mood_name: str, now: float) -> bool:
        key = str(mood_name or "").strip().lower()
        min_s = float(self.cfg.get("emotion_hold_s", 2.0))
        if key == self._last_resolved_mood:
            return False
        if (now - self._last_mood_apply_ts) < max(0.2, min_s):
            return False
        return True

    def _idle_action(self) -> OledAction:
        idle = str(self.cfg.get("idle_bitmap", "normal"))
        return OledAction(mode="bitmap", name=idle)
