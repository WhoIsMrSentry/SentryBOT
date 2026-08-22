"""Resolve conflicts between interaction events, polled emotions, and operational state."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from .mapper import FaceMapper, OledAction


_DOMINANT_OPERATIONAL: Set[str] = {
    "listening", "thinking", "speaking", "sleeping", "alert",
}

_PASSIVE_OPERATIONAL: Set[str] = {
    "idle", "boot", "active", "maintenance",
    "charging", "charged", "low_battery",
}

_LISTEN_START = {"wakeword.detected", "speech.listen.start"}
_LISTEN_END = {"speech.listen.end"}

_FORCE_EMOTION_LABELS = {"anger", "angry", "furious", "fear", "scared", "surprise", "surprised"}

_SPEAK_START = {"speech.start"}
_SPEAK_END = {"speech.end"}


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
        self._listen_until: float = 0.0
        self._speak_until: float = 0.0
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

        if key in _LISTEN_START:
            self._listen_until = now + float(self.cfg.get("listen_session_hold_s", 120.0))
            listen = self.mapper.from_interaction_event("speech.listen.start")
            return FaceDecision(action=listen, priority=max(priority, 78), source="event")

        if key in _LISTEN_END:
            self._listen_until = 0.0
            return FaceDecision(action=baseline or self._idle_action(), priority=70, source="event")

        if key in _SPEAK_START:
            self._speak_until = now + float(self.cfg.get("speak_session_hold_s", 90.0))
            think = self.mapper.from_interaction_event("agent.thinking")
            return FaceDecision(action=think, priority=max(priority, 74), source="event")

        if key in _SPEAK_END:
            self._speak_until = 0.0
            if self._listen_active(now):
                listen = self.mapper.from_interaction_event("speech.listen.start")
                return FaceDecision(action=listen, priority=72, source="event")
            return FaceDecision(action=baseline or self._idle_action(), priority=68, source="event")

        if key.startswith("emotion:"):
            label = key.split(":", 1)[1]
            mood_action = self.mapper.from_emotions([label])
            force_emotion = label in _FORCE_EMOTION_LABELS
            if (self._listen_active(now) or self._speak_active(now)) and not force_emotion:
                return FaceDecision(action=mood_action, priority=priority, source="event", apply=False)
            if not force_emotion and not self._emotion_stable(mood_action.name, now):
                return FaceDecision(action=mood_action, priority=priority, source="event", apply=False)
            boosted = 88 if force_emotion else max(priority, 62)
            return FaceDecision(action=mood_action, priority=boosted, source="event")

        if key in {"autonomy.blink", "autonomy.look_around", "autonomy.stretch"}:
            return FaceDecision(action=action, priority=min(priority, 45), source="event")

        return FaceDecision(action=action, priority=priority, source="event")

    def from_state(
        self,
        operational: str,
        emotions: List[str],
        *,
        op_changed: bool,
        emo_changed: bool,
    ) -> Optional[FaceDecision]:
        now = time.time()
        op = str(operational or "idle").strip().lower()

        if self._listen_active(now) or self._speak_active(now):
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
            return FaceDecision(action=mapped, priority=60, source="emotion")

        if op_changed:
            mapped = self.mapper.from_operational(op)
            return FaceDecision(action=mapped, priority=50 if mapped.mode == "bitmap" else 52, source="state")

        return None

    def listen_session_active(self) -> bool:
        return self._listen_active(time.time())

    def speak_session_active(self) -> bool:
        return self._speak_active(time.time())

    def session_active(self) -> bool:
        now = time.time()
        return self._listen_active(now) or self._speak_active(now)

    def should_clear_activity(self, now: float, hold_until: float) -> bool:
        if self._listen_active(now) or self._speak_active(now):
            return False
        return now >= hold_until

    def note_applied_mood(self, mood_name: str) -> None:
        self._last_resolved_mood = str(mood_name or "").strip().lower()
        self._last_mood_apply_ts = time.time()

    def _listen_active(self, now: float) -> bool:
        return now < self._listen_until

    def _speak_active(self, now: float) -> bool:
        return now < self._speak_until

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
