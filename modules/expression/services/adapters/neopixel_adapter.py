"""Neopixel adapter for ExpressionArbiter.

Translates semantic expression calls into Neopixel service HTTP requests.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from modules.common.http_client import AsyncHTTPClient, get_http_client

logger = logging.getLogger("expression.adapter.neopixel")


class NeopixelAdapter:
    """Adapter for Neopixel service (LEDs)."""
    
    def __init__(self, gateway_url: str = "http://127.0.0.1:8080", timeout: float = 2.0):
        self._gateway = gateway_url.rstrip("/")
        self._client = get_http_client(self._gateway, timeout)
    
    async def set_effect(
        self,
        effect: str,
        color: tuple[int, int, int] | list[int],
        speed: float = 1.0,
        duration_s: float = 3.0,
    ) -> bool:
        """Set a Neopixel effect with semantic color/animation."""
        rgb = list(color)
        try:
            # Try primary endpoint
            resp = await self._client.post(
                "/neopixel/emote",
                json={
                    "effect": effect,
                    "color": rgb,
                    "speed": round(speed, 3),
                    "duration": round(duration_s, 2),
                },
            )
            return resp.status_code == 200
        except Exception as e:
            logger.debug("Neopixel set_effect failed: %s", e)
            # Fallback: try animate endpoint
            try:
                resp = await self._client.post(
                    "/neopixel/animate",
                    json={
                        "name": effect,
                        "color": rgb,
                        "iterations": max(1, int(duration_s / 2)),
                    },
                )
                return resp.status_code == 200
            except Exception as e2:
                logger.warning("Neopixel fallback also failed: %s", e2)
                return False
    
    async def set_color(
        self,
        color: tuple[int, int, int] | list[int],
        duration_s: float = 0.0,
    ) -> bool:
        """Direct RGB color set (no animation)."""
        try:
            resp = await self._client.post(
                "/neopixel/fill",
                json={"color": list(color), "duration": duration_s},
            )
            return resp.status_code == 200
        except Exception as e:
            logger.debug("Neopixel set_color failed: %s", e)
            return False
    
    async def turn_off(self) -> bool:
        """Turn off LEDs."""
        return await self.set_effect("OFF", (0, 0, 0), speed=1.0, duration_s=0.5)


__all__ = ["NeopixelAdapter"]