"""Timeline and journaling helpers for AutonomyBrain."""
from __future__ import annotations

import datetime


class TimelineMixin:
    """Keeps a lightweight daily journal of interactions."""

    def _reset_daily_timeline(self) -> None:
        self.timeline = {
            "day": datetime.date.today(),
            "conversations": 0,
            "people": {},
            "favorite_question": None,
            "favorite_question_score": 0,
            "events": [],
            "emotions": {},
        }

    def _ensure_timeline_day(self) -> None:
        today = datetime.date.today()
        if not hasattr(self, "timeline") or self.timeline.get("day") != today:
            self._reset_daily_timeline()

    def _apply_timeline_event(self, event_name: str) -> None:
        self._ensure_timeline_day()
        events = self.timeline.setdefault("events", [])
        if isinstance(events, list):
            events.append({"event": event_name, "time": datetime.datetime.now().strftime("%H:%M:%S")})
            if len(events) > 50:
                self.timeline["events"] = events[-50:]

    def _update_timeline_emotion(self, emotion: str) -> None:
        self._ensure_timeline_day()
        emotions = self.timeline.setdefault("emotions", {})
        if isinstance(emotions, dict):
            emotions[emotion] = emotions.get(emotion, 0) + 1

    def _log_conversation(self, text: str) -> None:
        self._ensure_timeline_day()
        self.timeline["conversations"] = self.timeline.get("conversations", 0) + 1
        if "?" in text:
            score = len(text)
            if score > self.timeline.get("favorite_question_score", 0):
                self.timeline["favorite_question"] = text
                self.timeline["favorite_question_score"] = score

    def _track_person_stat(self, name: str) -> None:
        self._ensure_timeline_day()
        people = self.timeline.setdefault("people", {})
        people[name] = people.get(name, 0) + 1

    def _build_timeline_summary(self) -> str | None:
        conv = self.timeline.get("conversations", 0)
        people = self.timeline.get("people", {})
        favorite = self.timeline.get("favorite_question")
        if conv == 0 and not people and not favorite:
            return None
        parts: list[str] = []
        if conv:
            parts.append(f"Bugün {conv} sohbet yaptım")
        else:
            parts.append("Bugün kimseyle sohbet etmedim")
        if people:
            top = sorted(people.items(), key=lambda item: item[1], reverse=True)[:2]
            formatted = ", ".join(f"{name} ile {count} kez" for name, count in top)
            parts.append(f"En çok {formatted} görüştüm")
        if favorite:
            parts.append(f"En merak ettiğim soru: {favorite}")
        return ". ".join(parts) + "."

    def _deliver_timeline_summary(self) -> None:
        summary = self._build_timeline_summary()
        if summary:
            self._speak_with_mood(summary, emotion="joy")
        self._reset_daily_timeline()
