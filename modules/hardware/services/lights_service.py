"""
Production-ready HAL Lights Service.
Delegates to the existing Neopixel and Arduino Laser services via ServiceClient.
"""
import logging
from typing import Optional, List

logger = logging.getLogger("hardware.lights")


class LightsService:
    """
    Controls NeoPixel LED strips and Laser pointers via ServiceClient HTTP calls.
    """

    def __init__(self, client):
        self.client = client

    def set_effect(
        self,
        effect: str,
        emotions: Optional[List[str]] = None,
        color: Optional[tuple] = None,
        duration: Optional[float] = None,
    ) -> Optional[dict]:
        """
        Apply a NeoPixel animation effect (BREATHE, PULSE, SPINNER, WAVE, FIRE, etc.).
        """
        try:
            result = self.client.set_neopixel(effect, emotions=emotions, color=color, duration=duration)
            logger.info("NeoPixel effect '%s' applied -> %s", effect, result)
            return result
        except Exception as e:
            logger.error("NeoPixel effect failed: %s", e)
            return None

    def fill_color(self, r: int, g: int, b: int) -> None:
        """Fill all LEDs with a solid color."""
        try:
            self.client.fill_neopixel_color(r, g, b)
        except Exception as e:
            logger.error("NeoPixel fill failed: %s", e)

    def apply_preset(self, name: str) -> Optional[dict]:
        """Apply a named preset palette."""
        try:
            return self.client.apply_neopixel_preset(name)
        except Exception as e:
            logger.error("NeoPixel preset '%s' failed: %s", name, e)
            return None

    def set_laser(self, on: bool, laser_id: int = 1, both: bool = False) -> Optional[dict]:
        """Control cross-lasers via Arduino."""
        try:
            result = self.client.set_laser(on, id=laser_id, both=both)
            logger.info("Laser set on=%s id=%d both=%s -> %s", on, laser_id, both, result)
            return result
        except Exception as e:
            logger.error("Laser control failed: %s", e)
            return None
