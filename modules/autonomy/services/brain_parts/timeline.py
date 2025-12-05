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
        }

    def _ensure_timeline_day(self) -> None:
        today = datetime.date.today()
        if self.timeline.get("day") != today:
            self._reset_daily_timeline()

    def _log_conversation(self, text: str) -> None:
        if not hasattr(self, "timeline"):
            self._reset_daily_timeline()
        self.timeline["conversations"] = self.timeline.get("conversations", 0) + 1
        if "?" in text:
            score = len(text)
            if score > self.timeline.get("favorite_question_score", 0):
                self.timeline["favorite_question"] = text
                self.timeline["favorite_question_score"] = score

    def _track_person_stat(self, name: str) -> None:
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
