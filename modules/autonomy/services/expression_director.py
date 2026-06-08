"""Multi-modal expression director.

Fires a single, coherent emotional expression across every output modality at
once — eyes (OLED), LEDs (NeoPixel), ears (PiServo, via interaction event),
optional head pose and optional speech with a matching TTS tone.

All modalities are resolved from the shared canonical emotion vocabulary so they
stay in sync. Every call is best-effort: a failing modality never blocks the
others, keeping the robot alive even if one subsystem is down.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger("autonomy.expression")

try:
    from modules.common.emotion_vocab import emotion_render as _emotion_render
except Exception:  # pragma: no cover - optional dependency
    _emotion_render = None


def _safe(label: str, fn) -> bool:
    try:
        fn()
        return True
    except Exception:
        logger.debug("expression modality failed: %s", label, exc_info=True)
        return False


class ExpressionDirector:
    """Coordinates eyes + LEDs + ears + head + voice for one emotion."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def express(
        self,
        emotion: str,
        *,
        say: Optional[str] = None,
        language: Optional[str] = None,
        move_head: Optional[Tuple[int, int]] = None,
    ) -> str:
        """Render ``emotion`` across all modalities; returns the canonical label."""
        if _emotion_render is not None:
            render = _emotion_render(emotion)
            canon = render.canonical
            effect = render.effect
            oled = render.oled
            color = list(render.rgb)
            tone = render.tone
        else:  # minimal fallback when shared vocab is unavailable
            canon = str(emotion or "neutral").strip().lower()
            effect, oled, color, tone = "BREATHE", "normal", [120, 120, 140], "neutral"

        modalities = []
        if _safe("leds", lambda: self.client.set_neopixel(effect, emotions=[canon], color=color)):
            modalities.append("leds")
        if _safe("eyes", lambda: self.client.oled_show(oled)):
            modalities.append("eyes")
        # interaction event drives ears (piservo bridge) + any other subscribers
        if _safe("ears", lambda: self.client.push_interaction_event(f"emotion:{canon}")):
            modalities.append("ears")
        if move_head is not None:
            pan, tilt = move_head
            if _safe("head", lambda: self.client.move_head(int(pan), int(tilt))):
                modalities.append("head")
        if say:
            if _safe("voice", lambda: self.client.speak(say, tone=tone, language=language)):
                modalities.append("voice")

        logger.debug("expressed %s via %s", canon, modalities)
        return canon


__all__ = ["ExpressionDirector"]
