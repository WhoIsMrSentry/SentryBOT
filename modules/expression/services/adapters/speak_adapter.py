"""Speak/TTS adapter for ExpressionArbiter.

Translates semantic expression calls into Speak service HTTP requests
with voice tone, pitch shift, and speed.
"""

from __future__ import annotations

import logging

from modules.common.http_client import AsyncHTTPClient, get_http_client

logger = logging.getLogger("expression.adapter.speak")


class SpeakAdapter:
    """Adapter for Speak/TTS service."""
    
    def __init__(self, gateway_url: str = "http://127.0.0.1:8080", timeout: float = 4.0):
        self._gateway = gateway_url.rstrip("/")
        self._client = get_http_client(self._gateway, timeout)
    
    async def say(
        self,
        text: str,
        tone: str = "neutral",
        language: str = "tr",
        pitch_shift: float = 0.0,
        speed: float = 1.0,
    ) -> bool:
        """Speak text with emotion-appropriate voice parameters."""
        try:
            # Try primary say endpoint
            resp = await self._client.post(
                "/speak/say",
                json={
                    "text": text,
                    "tone": tone,
                    "language": language,
                    "pitch_shift": round(pitch_shift, 3),
                    "speed": round(speed, 3),
                },
            )
            if resp.status_code == 200:
                return True
            # Fallback: minimal say
            resp2 = await self._client.post(
                "/speak/say",
                json={"text": text, "language": language},
            )
            return resp2.status_code == 200
        except Exception as e:
            logger.warning("Speak failed: %s", e)
            return False


__all__ = ["SpeakAdapter"]