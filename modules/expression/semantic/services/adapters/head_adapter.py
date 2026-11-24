"""Head/Servo adapter for ExpressionArbiter.

Translates semantic expression calls into Arduino serial / PiServo
servo position commands.
"""

from __future__ import annotations

import asyncio
import logging
import time

from modules.common.http_client import get_http_client
from modules.arduino_serial.contract import SERVO_INDEX_PAN, SERVO_INDEX_TILT, build_set_servo_cmd

logger = logging.getLogger("expression.adapter.head")


class HeadAdapter:
    """Adapter for head/servo control (Arduino serial via gateway)."""

    def __init__(
        self,
        gateway_url: str = "http://127.0.0.1:8080",
        timeout: float = 1.0,
        *,
        enabled: bool = True,
        fail_cooldown_s: float = 30.0,
    ):
        self._gateway = gateway_url.rstrip("/")
        self._client = get_http_client(self._gateway, timeout)
        self.enabled = bool(enabled)
        self._fail_cooldown_s = max(0.0, float(fail_cooldown_s))
        self._cooldown_until = 0.0

    async def move_head(self, pan: int, tilt: int) -> bool:
        """Move head to pan/tilt angles concurrently (pan 30-150, tilt 60-120, 90=center)."""
        if not self.enabled or time.monotonic() < self._cooldown_until:
            return False
        try:
            pan = max(30, min(150, int(pan)))
            tilt = max(60, min(120, int(tilt)))

            resp_pan, resp_tilt = await asyncio.gather(
                self._client.post(
                    "/arduino/request",
                    json=build_set_servo_cmd(SERVO_INDEX_PAN, pan),
                ),
                self._client.post(
                    "/arduino/request",
                    json=build_set_servo_cmd(SERVO_INDEX_TILT, tilt),
                ),
            )
            st_pan = int(getattr(resp_pan, "status_code", 0) or 0)
            st_tilt = int(getattr(resp_tilt, "status_code", 0) or 0)
            if st_pan in (404, 503) or st_tilt in (404, 503):
                self._cooldown_until = time.monotonic() + max(self._fail_cooldown_s, 60.0)
                logger.debug("Head hardware endpoint unavailable (%s/%s); pausing retries.", st_pan, st_tilt)
                return False
            if st_pan == 200 and st_tilt == 200:
                self._cooldown_until = 0.0
                return True
            if self._fail_cooldown_s > 0.0:
                self._cooldown_until = time.monotonic() + self._fail_cooldown_s
            return False
        except Exception as e:
            if self._fail_cooldown_s > 0.0:
                self._cooldown_until = time.monotonic() + self._fail_cooldown_s
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