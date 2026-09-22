"""System 1 Reflex Engine — LayaEngine Proxy (Backward Compatible).

This class is maintained for backward compatibility. All core intelligence
is now provided by modules.agent_core.services.laya_engine.LayaEngine.

Original İki Katmanlı Zihin (Two-Layered Mind) concept is preserved:
1. Millisecond body language reactions while waiting for LLM (System 2).
2. Verbal fillers for long-running queries.

The proxy transparently delegates to LayaEngine when available, falling back
to the original static behavior when it is not.
"""

from __future__ import annotations
import logging
import random
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("autonomy.system1_reflex")

# Original constants preserved for backward compatibility
THINKING_FILLERS_TR = [
    "Hmm...",
    "Hemen bakıyorum...",
    "Bir düşüneyim...",
    "Hımm, anladım...",
    "Bakalım...",
]

THINKING_FILLERS_EN = [
    "Hmm...",
    "Let me check...",
    "Thinking...",
    "One second...",
]


class System1ReflexEngine:
    """DEPRECATED — Transparent proxy to LayaEngine.

    Preserves the original API surface so existing callers in AutonomyBrain
    continue to work. When LayaEngine is available, delegates to it for
    mood-aware fillers and affective body language. Falls back to static
    behavior otherwise.
    """

    def __init__(self, language: str = "tr") -> None:
        self.language = language
        self._laya: Any = None
        self._laya_checked = False
        self._last_filler_ts = 0.0
        self._filler_cooldown_s = 15.0
        logger.info("System1ReflexEngine initialized (LayaEngine proxy mode)")

    def _get_laya(self) -> Any:
        """Lazy-load the LayaEngine singleton."""
        if self._laya is not None:
            return self._laya
        if self._laya_checked:
            return None
        self._laya_checked = True
        try:
            from modules.agent_core.services.laya_engine import LayaEngine
            self._laya = LayaEngine.get_instance()
            if self._laya and getattr(self._laya, '_is_available', False):
                logger.info("System1ReflexEngine: Successfully connected to LayaEngine")
            else:
                logger.info("System1ReflexEngine: LayaEngine found but model not loaded yet")
        except Exception as exc:
            logger.debug("System1ReflexEngine: LayaEngine not available: %s", exc)
        return self._laya

    def get_thinking_body_pose(self) -> Dict[str, Any]:
        """Return a natural thinking body pose for the robot.

        When LayaEngine is available, uses affective reaction for LED color.
        Otherwise falls back to static defaults.
        """
        laya = self._get_laya()
        led_color = "#30e3ca"
        if laya and getattr(laya, '_is_available', False):
            try:
                reaction = laya.get_affective_reaction("neutral")
                led_color = reaction.get("led_color", led_color)
            except Exception:
                pass

        return {
            "head": {"pan": random.choice([86, 94]), "tilt": 102},
            "ears": {"left": 80, "right": 70},
            "eyes": {"mode": "animation", "name": "thinking"},
            "leds": {"mode": "thinking", "color": led_color},
        }

    def should_emit_verbal_filler(self, wait_elapsed_s: float) -> bool:
        """Check if we should emit a verbal filler after waiting.

        Triggers after 1.2s of waiting, with a cooldown to prevent spam.
        """
        if wait_elapsed_s < 1.2:
            return False
        now = time.time()
        if now - self._last_filler_ts < self._filler_cooldown_s:
            return False
        self._last_filler_ts = now
        return True

    def get_verbal_filler(self, mood: str = "neutral") -> str:
        """Return a random thinking filler phrase.

        When LayaEngine is available and mood_aware is enabled, uses mood-aware
        fillers. Otherwise falls back to static phrase lists.

        Args:
            mood: Current dominant emotion (optional, defaults to "neutral")
        """
        laya = self._get_laya()
        if laya and getattr(laya, '_is_available', False):
            try:
                if hasattr(laya, 'get_filler_with_affect') and mood != "neutral":
                    filler = laya.get_filler_with_affect(self.language, mood=mood)
                    if filler:
                        return filler
                else:
                    filler = laya.get_instant_filler(self.language)
                    if filler:
                        return filler
            except Exception:
                pass

        # Static fallback
        if self.language.startswith("en"):
            return random.choice(THINKING_FILLERS_EN)
        return random.choice(THINKING_FILLERS_TR)
