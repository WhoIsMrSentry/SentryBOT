"""Speech and tone helpers for AutonomyBrain."""
from __future__ import annotations

import datetime
import logging
import time

logger = logging.getLogger("autonomy.vocal")


class VocalMixin:
    """Adds speaking helpers that respect robot mood."""

    def _generate_monologue(self) -> None:
        if not self.config.get("llm", {}).get("enabled", False):
            return

        template = self.config.get("llm", {}).get("prompt_template", "")
        now = time.time()
        happiness = int(self.mood["happiness"])
        energy = int(self.mood["energy"])
        is_bored = "Evet" if self.state["is_bored"] else "Hayır"
        last_interaction_ago = int(now - self.state["last_interaction"])
        current_time = datetime.datetime.now().strftime("%H:%M")

        try:
            prompt = template.format(
                happiness=happiness,
                energy=energy,
                is_bored=is_bored,
                last_interaction_ago=last_interaction_ago,
                time=current_time,
            )

            resp = self.client.chat(prompt)
            if resp and "answer" in resp:
                text = resp["answer"].strip('"')
                logger.info("Monologue: %s", text)
                self._speak_with_mood(text, emotion="neutral")
                self.memory.add_event(f"Said to myself: {text}")
        except Exception as exc:
            logger.error("Monologue failed: %s", exc)

    def _speak_with_mood(self, text: str, emotion: str | None = None) -> None:
        if not text:
            return
        tone = self._tone_profile(emotion)
        try:
            self.client.speak(text, tone=tone)
        except Exception as exc:  # pragma: no cover - best effort speech
            logger.debug("Failed to speak with tone %s: %s", tone, exc)

    def _tone_profile(self, emotion: str | None = None) -> dict:
        emotion = emotion or self.state.get("last_emotion") or self.mood.get_dominant_emotion() or "neutral"
        profiles = {
            "joy": {"rate": 190, "volume": 1.0},
            "sadness": {"rate": 150, "volume": 0.75},
            "curiosity": {"rate": 185, "volume": 0.9},
            "tired": {"rate": 140, "volume": 0.65},
            "fear": {"rate": 200, "volume": 0.9},
            "neutral": {"rate": 170, "volume": 0.85},
        }
        return profiles.get(emotion, profiles["neutral"])
