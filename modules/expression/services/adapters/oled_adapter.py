"""OLED Faces adapter for ExpressionArbiter.

Translates semantic expression calls into OLED face service HTTP requests.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from modules.common.http_client import AsyncHTTPClient, get_http_client

logger = logging.getLogger("expression.adapter.oled")


class OledAdapter:
    """Adapter for OLED Faces service (SSD1306 animations)."""
    
    def __init__(self, gateway_url: str = "http://127.0.0.1:8080", timeout: float = 2.0):
        self._gateway = gateway_url.rstrip("/")
        self._client = get_http_client(self._gateway, timeout)
    
    async def play_animation(
        self,
        name: str,
        duration_s: float = 3.0,
        loop: bool = False,
    ) -> bool:
        """Play an OLED face animation."""
        try:
            resp = await self._client.post(
                "/oled_faces/animate",
                json={
                    "name": name,
                    "duration_s": round(duration_s, 2),
                    "loop": loop,
                },
            )
            if resp.status_code == 200:
                return True
            # Fallback: event-based animation
            resp2 = await self._client.post(
                "/oled_faces/event",
                json={"type": f"anim:{name}", "loop": loop},
            )
            return resp2.status_code == 200
        except Exception as e:
            logger.warning("OLED play_animation failed: %s", e)
            return False
    
    async def show_bitmap(self, bitmap: str) -> bool:
        """Show a static OLED bitmap."""
        try:
            resp = await self._client.post(
                "/oled_faces/show",
                json={"name": bitmap},
            )
            return resp.status_code == 200
        except Exception as e:
            logger.debug("OLED show_bitmap failed: %s", e)
            return False
    
    async def show_eyes(self, expression: str) -> bool:
        """Alias for showing eye expression."""
        return await self.show_bitmap(expression)


__all__ = ["OledAdapter"]