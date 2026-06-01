"""Speech and tone helpers for AutonomyBrain."""
from __future__ import annotations

import datetime
import logging
import time

try:
    from modules.speak.services.lang_detect import detect_text_language
except ImportError:
    detect_text_language = None

logger = logging.getLogger("autonomy.vocal")


class VocalMixin:
    """Adds speaking helpers that respect robot mood."""

    def _generate_monologue(self) -> None:
        if not self.config.get("llm", {}).get("enabled", False):
            return
        if time.time() < float(getattr(self, "_llm_rate_limit_until", 0.0)):
            logger.debug("Monologue skipped (LLM rate limit cooldown active)")
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
            from modules.config_center.log_redact import redact_secrets

            msg = redact_secrets(exc)
            if "429" in msg:
                self._llm_rate_limit_until = time.time() + 90.0
                logger.warning("Monologue skipped for 90s (Gemini rate limit)")
                return
            logger.error("Monologue failed: %s", msg)

    def _speak_with_mood(self, text: str, emotion: str | None = None, language: str | None = None) -> None:
        if not text:
            return
        if not language and detect_text_language:
            language = detect_text_language(text, default="tr")
        tone = self._tone_profile(emotion)
        try:
            self.client.queue_action("speak", priority=50, ttl_ms=10000, payload={
                "text": text,
                "tone": tone,
                "language": language
            })
        except Exception as exc:  # pragma: no cover - best effort speech
            logger.debug("Failed to queue speech action: %s", exc)

    # Per-canonical-emotion prosody. Resolution goes through the shared emotion
    # vocabulary so aliases ("happy"->joy, "scared"->fear, "angry"->anger) all
    # collapse to the same voice as eyes/LEDs/ears.
    _EMOTION_TONES = {
        "joy": {"rate": 190, "volume": 1.0},
        "love": {"rate": 185, "volume": 0.95},
        "excitement": {"rate": 205, "volume": 1.0},
        "surprise": {"rate": 200, "volume": 1.0},
        "curiosity": {"rate": 185, "volume": 0.9},
        "sadness": {"rate": 150, "volume": 0.75},
        "worried": {"rate": 165, "volume": 0.8},
        "tired": {"rate": 140, "volume": 0.65},
        "bored": {"rate": 150, "volume": 0.7},
        "fear": {"rate": 200, "volume": 0.9},
        "anger": {"rate": 195, "volume": 1.0},
        "furious": {"rate": 205, "volume": 1.0},
        "confusion": {"rate": 165, "volume": 0.85},
        "disgust": {"rate": 165, "volume": 0.85},
        "neutral": {"rate": 170, "volume": 0.85},
    }
    # Fallback by canonical TTS tone name when a specific emotion isn't mapped.
    _TONE_NAME_PROFILES = {
        "joy": {"rate": 190, "volume": 1.0},
        "excited": {"rate": 200, "volume": 1.0},
        "sadness": {"rate": 150, "volume": 0.75},
        "neutral": {"rate": 170, "volume": 0.85},
    }

    def _tone_profile(self, emotion: str | None = None) -> dict:
        emotion = emotion or self.state.get("last_emotion") or self.mood.get_dominant_emotion() or "neutral"
        try:
            from modules.common.emotion_vocab import get_vocab

            vocab = get_vocab()
            canon = vocab.canonical(emotion)
            if canon in self._EMOTION_TONES:
                return dict(self._EMOTION_TONES[canon])
            tone_name = vocab.render(emotion).tone
            return dict(self._TONE_NAME_PROFILES.get(tone_name, self._TONE_NAME_PROFILES["neutral"]))
        except Exception:
            return dict(self._EMOTION_TONES.get(str(emotion).lower(), self._EMOTION_TONES["neutral"]))
