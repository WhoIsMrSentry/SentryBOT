"""
Production-ready HAL Audio Service.
Delegates to the existing Speak service and Arduino buzzer via ServiceClient.
"""
import logging
from typing import Optional

logger = logging.getLogger("hardware.audio")


class AudioService:
    """
    Controls TTS output (pyttsx3/piper) and hardware buzzer sounds via ServiceClient.
    """

    def __init__(self, client):
        self.client = client

    def speak(self, text: str, tone: Optional[str] = None, engine: Optional[str] = None, language: Optional[str] = None) -> bool:
        """
        Speak text via the TTS microservice.
        Returns True on success.
        """
        try:
            result = self.client.speak(text, tone=tone, engine=engine, language=language)
            logger.info("TTS: '%s' -> %s", text[:50], result)
            return bool(result)
        except Exception as e:
            logger.error("TTS failed: %s", e)
            return False

    def beep(self, out: str = "loud", freq: int = 2200, ms: int = 60) -> Optional[dict]:
        """Play a buzzer tone via Arduino."""
        try:
            result = self.client.set_buzzer(out=out, freq=freq, ms=ms)
            logger.info("Buzzer beep: %s %dHz %dms -> %s", out, freq, ms, result)
            return result
        except Exception as e:
            logger.error("Buzzer failed: %s", e)
            return None

    def play_sound(self, name: str, out: str = "loud") -> Optional[dict]:
        """Play a named sound effect (walle, bb8, etc.) via Arduino."""
        try:
            result = self.client.play_sound(name, out=out)
            logger.info("Sound play '%s' -> %s", name, result)
            return result
        except Exception as e:
            logger.error("Sound play failed: %s", e)
            return None

    def set_lcd(self, top: str = "", bottom: str = "", lcd_id: int = 0) -> Optional[dict]:
        """Write text to the LCD display."""
        try:
            return self.client.set_lcd(top=top, bottom=bottom, id=lcd_id)
        except Exception as e:
            logger.error("LCD write failed: %s", e)
            return None

    def set_oled(self, action: str = "show", name: str = "normal") -> Optional[dict]:
        """Control OLED face display."""
        try:
            if action == "anim":
                return self.client.oled_anim(name)
            elif action == "stop":
                return self.client.oled_stop()
            elif action == "logo":
                return self.client.oled_logo()
            else:
                return self.client.oled_show(name)
        except Exception as e:
            logger.error("OLED %s failed: %s", action, e)
            return None
