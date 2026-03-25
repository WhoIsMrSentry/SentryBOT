"""
Production-ready HAL Servo Service.
Delegates to the existing ServiceClient HTTP layer (which talks to Arduino via Gateway).
"""
import logging
from typing import Optional

logger = logging.getLogger("hardware.servo")


class ServoService:
    """
    Interfaces with the Arduino PCA9685 servo system via ServiceClient HTTP calls.
    This is NOT a direct serial connection — SentryBOT uses a microservice architecture
    where arduino_serial runs its own FastAPI, and we communicate via HTTP.
    """

    def __init__(self, client):
        """
        Args:
            client: An autonomy ServiceClient instance (modules.autonomy.services.client).
        """
        self.client = client

    def move_head(self, pan: int, tilt: int, speed: float = 0.8) -> dict:
        """
        Commands the head pan/tilt via ServiceClient -> Arduino.
        Returns the response dict from Arduino (contains 'ok' field).
        """
        try:
            result = self.client.move_head(pan, tilt, speed)
            logger.info("Servo moved: pan=%d tilt=%d -> %s", pan, tilt, result)
            return result or {"ok": False, "error": "no_response"}
        except Exception as e:
            logger.error("Servo move_head failed: %s", e)
            return {"ok": False, "error": str(e)}

    def run_animation(self, name: str, speed: float = 1.0, loop: bool = False) -> Optional[dict]:
        """Trigger a named servo animation via the Animate service."""
        try:
            result = self.client.run_animation(name, speed=speed, loop=loop)
            logger.info("Servo animation '%s' triggered -> %s", name, result)
            return result
        except Exception as e:
            logger.error("Servo animation '%s' failed: %s", name, e)
            return None
