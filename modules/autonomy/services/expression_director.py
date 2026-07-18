from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger("autonomy.expression")


class ExpressionDirector:
    """Publishes semantic expression intent to the single expression owner."""

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
        canonical = str(emotion or "neutral").strip().lower()
        data = {
            "emotion": canonical,
            "attention": "user" if say else "internal",
            "speaking": bool(say),
        }
        if move_head is not None:
            data["head_hint"] = {"pan": int(move_head[0]), "tilt": int(move_head[1])}
        try:
            self.client.set_expression_event(f"emotion:{canonical}", data)
        except Exception:
            logger.debug("semantic expression publish failed", exc_info=True)
        if say:
            try:
                self.client.speak_preferred(say, tone=canonical, language=language)
            except Exception:
                logger.debug("expression speech failed", exc_info=True)
        return canonical


__all__ = ["ExpressionDirector"]
