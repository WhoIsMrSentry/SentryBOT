"""Head/Servo adapter for ExpressionArbiter.

Translates semantic expression calls into Arduino serial / PiServo
servo position commands.
"""

from __future__ import annotations

import logging

from modules.common.http_client import AsyncHTTPClient, get_http_client
from modules.arduino_serial.contract import SERVO_INDEX_PAN, SERVO_INDEX_TILT, build_set_servo_cmd

logger = logging.getLogger("expression.adapter.head")


class HeadAdapter:
    """Adapter for head/servo control (Arduino serial via gateway)."""
    
    def __init__(self, gateway_url: str = "http://127.0.0.1:8080", timeout: float = 1.0):
        self._gateway = gateway_url.rstrip("/")
        self._client = get_http_client(self._gateway, timeout)
    
    async def move_head(self, pan: int, tilt: int) -> bool:
        """Move head to pan/tilt angles (0-180, 90=center)."""
        try:
            # Clamp to safe ranges
            pan = max(30, min(150, int(pan)))
            tilt = max(60, min(120, int(tilt)))
            
            resp = await self._client.post(
                "/arduino/request",
                json=build_set_servo_cmd(SERVO_INDEX_PAN, pan),
            )
            if getattr(resp, "status_code", 0) != 200:
                return False
            resp2 = await self._client.post(
                "/arduino/request",
                json=build_set_servo_cmd(SERVO_INDEX_TILT, tilt),
            )
            return getattr(resp2, "status_code", 0) == 200
        except Exception as e:
            logger.debug("Head move failed: %s", e)
            return False


class PiServoAdapter:
    """Adapter for PiServo (ears)."""
    
    def __init__(self, gateway_url: str = "http://127.0.0.1:8080", timeout: float = 1.0):
        self._gateway = gateway_url.rstrip("/")
        self._client = get_http_client(self._gateway, timeout)
    
    async def set_ears(self, position: str = "neutral") -> bool:
        """Set ear servo position."""
        try:
            resp = await self._client.post(
                "/piservo/emotion",
                json={"name": position},
            )
            if resp.status_code == 200:
                return True
            # Fallback: direct angle set
            angle_map = {"neutral": 90, "joy": 110, "sadness": 70, "anger": 80}
            angle = angle_map.get(position, 90)
            resp2 = await self._client.post(
                "/piservo/set",
                params={"left": angle, "right": 180 - angle},
            )
            return resp2.status_code == 200
        except Exception as e:
            logger.debug("Ears set failed: %s", e)
            return False


__all__ = ["HeadAdapter", "PiServoAdapter"]