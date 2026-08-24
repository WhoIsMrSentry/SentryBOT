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
        """Play an OLED face animation.

        The oled_faces router exposes POST /manual {mode, name}
        (mode="animation") - there is no /animate endpoint.
        """
        try:
            resp = await self._client.post(
                "/oled_faces/manual",
                json={"mode": "animation", "name": name},
            )
            return resp.status_code == 200
        except Exception as e:
            logger.warning("OLED play_animation failed: %s", e)
            return False

    async def show_bitmap(self, bitmap: str) -> bool:
        """Show a static OLED bitmap via POST /manual (mode="bitmap")."""
        try:
            resp = await self._client.post(
                "/oled_faces/manual",
                json={"mode": "bitmap", "name": bitmap},
            )
            return resp.status_code == 200
        except Exception as e:
            logger.debug("OLED show_bitmap failed: %s", e)
            return False
    
    async def show_eyes(self, expression: str) -> bool:
        """Alias for showing eye expression."""
        return await self.show_bitmap(expression)


__all__ = ["OledAdapter"]