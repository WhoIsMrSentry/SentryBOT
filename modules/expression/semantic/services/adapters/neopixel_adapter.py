"""Neopixel adapter for ExpressionArbiter.

Translates semantic expression calls into Neopixel service HTTP requests.
"""

from __future__ import annotations

import logging

from modules.common.http_client import get_http_client

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
        effect_name = str(effect or "BREATHE").strip().upper()
        if effect_name == "OFF":
            return await self.turn_off()
        rgb = [int(c) & 255 for c in list(color)[:3]]
        while len(rgb) < 3:
            rgb.append(0)
        iterations = max(1, int(round(max(0.5, float(duration_s)) / 2.0)))
        try:
            resp = await self._client.post(
                "/neopixel/animate",
                json={
                    "name": effect_name,
                    "color": f"{rgb[0]},{rgb[1]},{rgb[2]}",
                    "r": rgb[0],
                    "g": rgb[1],
                    "b": rgb[2],
                    "iterations": iterations,
                    "speed": float(speed),
                },
            )
            if resp.status_code == 200:
                return True
        except Exception as e:
            logger.debug("Neopixel set_effect animate failed: %s", e)
        # Fallback: direct RGB fill
        return await self.set_color(rgb, duration_s=duration_s)

    async def set_color(
        self,
        color: tuple[int, int, int] | list[int],
        duration_s: float = 0.0,
    ) -> bool:
        """Direct RGB color set (no animation)."""
        rgb = list(color)
        try:
            # POST /neopixel/fill takes query param `r_` (FastAPI alias avoiding Python keyword)
            resp = await self._client.post(
                "/neopixel/fill",
                params={
                    "r_": int(rgb[0]) & 255,
                    "g": int(rgb[1]) & 255,
                    "b": int(rgb[2]) & 255,
                },
            )
            return resp.status_code == 200
        except Exception as e:
            logger.debug("Neopixel set_color failed: %s", e)
            return False

    async def turn_off(self) -> bool:
        """Turn off LEDs cleanly via /neopixel/clear (or black fill fallback)."""
        try:
            resp = await self._client.post("/neopixel/clear")
            if resp.status_code == 200:
                return True
        except Exception as e:
            logger.debug("Neopixel turn_off clear failed: %s", e)
        return await self.set_color((0, 0, 0))


__all__ = ["NeopixelAdapter"]