"""
Production-ready Action Router.
Maps validated/safe actions to the Hardware Abstraction Layer (HAL) services.
Returns action feedback strings for the Agent's proprioception system.

IMPORTANT: This router delegates to HAL services (which use ServiceClient HTTP).
It NEVER imports arduino_serial or any hardware driver directly.
"""
import logging
from typing import Dict, Any

logger = logging.getLogger("agent.router")


class ActionRouter:
    """
    Directs validated/safe actions from the Agent pipeline to HAL services.
    Returns feedback strings (SUCCESS/ERROR) for the WorldState proprioception loop.
    """

    def __init__(self, client):
        """
        Args:
            client: The existing ServiceClient from AutonomyBrain.
                    All routing goes through this single HTTP gateway.
        """
        self.client = client

        # Lazy-init HAL services (import here to avoid circular deps at module load)
        from modules.hardware.services.servo_service import ServoService
        from modules.hardware.services.lights_service import LightsService
        from modules.hardware.services.motor_service import MotorService
        from modules.hardware.services.audio_service import AudioService

        self.servo = ServoService(client)
        self.lights = LightsService(client)
        self.motor = MotorService(client)
        self.audio = AudioService(client)

    def route(self, action: Dict[str, Any]) -> str:
        """
        Routes a single action dict to its HAL service.
        Returns a feedback string for proprioception:
          "SUCCESS_*" on success
          "ERROR_*" on failure
          "IGNORED_UNKNOWN_ACTION" for unrecognized types
        """
        act_type = str(action.get("type", "")).strip().lower()
        attrs = action.get("attrs", {})

        try:
            # ── Servo (Head Movement) ──
            if act_type == "servo":
                pan = attrs.get("pan")
                tilt = attrs.get("tilt")
                if pan is not None or tilt is not None:
                    result = self.servo.move_head(
                        pan=int(pan) if pan is not None else 90,
                        tilt=int(tilt) if tilt is not None else 90,
                    )
                    return "SUCCESS_SERVO" if result and result.get("ok") else "ERROR_SERVO"
                return "ERROR_SERVO_NO_ATTRS"

            # ── Stepper (Wheels / Navigation) ──
            if act_type == "stepper":
                sid = int(attrs.get("id", 0))
                mode = str(attrs.get("mode", "vel"))
                value = int(attrs.get("value", attrs.get("velocity", 0)))
                return self.motor.drive(sid, mode, value)

            # ── Animations (Servo profiles: blink, look_around, stretch) ──
            if act_type == "anim":
                name = str(attrs.get("name", "blink"))
                result = self.servo.run_animation(name)
                return "SUCCESS_ANIM" if result else "ERROR_ANIM"

            # ── Lights (NeoPixel) ──
            if act_type == "lights":
                effect = str(attrs.get("mode", "BREATHE"))
                emotions = attrs.get("emotions")
                palette = attrs.get("palette")
                # If palette is set, route to preset
                if palette:
                    self.lights.apply_preset(palette)
                result = self.lights.set_effect(effect, emotions=emotions)
                return "SUCCESS_LIGHTS" if result else "ERROR_LIGHTS"

            # ── Laser ──
            if act_type == "laser":
                on = bool(attrs.get("on", False))
                lid = int(attrs.get("id", 1))
                both = bool(attrs.get("both", False))
                result = self.lights.set_laser(on, laser_id=lid, both=both)
                return "SUCCESS_LASER" if result else "ERROR_LASER"

            # ── Speak (TTS) ──
            if act_type in ("speak", "say"):
                text = str(attrs.get("text", ""))
                tone = attrs.get("tone")
                engine = attrs.get("engine")
                ok = self.audio.speak(text, tone=tone, engine=engine)
                return "SUCCESS_SPEAK" if ok else "ERROR_SPEAK"

            # ── Buzzer ──
            if act_type == "buzzer":
                out = str(attrs.get("out", "loud"))
                freq = int(attrs.get("freq", 2200))
                ms = int(attrs.get("ms", 60))
                result = self.audio.beep(out=out, freq=freq, ms=ms)
                return "SUCCESS_BUZZER" if result else "ERROR_BUZZER"

            # ── Sound Play (walle, bb8, etc.) ──
            if act_type == "sound_play":
                name = str(attrs.get("name", ""))
                out = str(attrs.get("out", "loud"))
                result = self.audio.play_sound(name, out=out)
                return "SUCCESS_SOUND" if result else "ERROR_SOUND"

            # ── LCD ──
            if act_type == "lcd":
                top = str(attrs.get("top", ""))
                bottom = str(attrs.get("bottom", ""))
                lid = int(attrs.get("id", 0))
                result = self.audio.set_lcd(top=top, bottom=bottom, lcd_id=lid)
                return "SUCCESS_LCD" if result else "ERROR_LCD"

            # ── OLED Faces ──
            if act_type == "oled":
                oled_action = str(attrs.get("action", "show"))
                name = str(attrs.get("name", "normal"))
                result = self.audio.set_oled(action=oled_action, name=name)
                return "SUCCESS_OLED" if result else "ERROR_OLED"

            # ── Arduino Raw Passthrough ──
            if act_type == "arduino":
                result = self.client.arduino_send(attrs)
                return "SUCCESS_ARDUINO_RAW" if result else "ERROR_ARDUINO_RAW"

            # ── System Module Control ──
            if act_type == "system":
                module = str(attrs.get("module", ""))
                sys_action = str(attrs.get("action", ""))
                result = self.client.system_control(module, sys_action)
                return f"SUCCESS_SYSTEM_{module}" if result else f"ERROR_SYSTEM_{module}"

            # ── Simple Robot Commands (stand, sit, home, zero_now) ──
            if act_type in ("stand", "sit", "home", "zero_now"):
                result = self.motor.robot_command(act_type)
                return f"SUCCESS_{act_type.upper()}" if result else f"ERROR_{act_type.upper()}"

            # ── Sensor Read Commands (ultra_read, imu_read, rfid_last) ──
            if act_type in ("ultra_read", "imu_read", "rfid_last"):
                result = self.client.read_sensor(act_type)
                return f"SUCCESS_{act_type.upper()}" if result else f"ERROR_{act_type.upper()}"

            # ── Event (interaction broadcast) ──
            if act_type == "event":
                event_name = str(attrs.get("name", "agent.action"))
                self.client.push_interaction_event(event_name, attrs)
                return "SUCCESS_EVENT"

            # ── Mode (not directly handled, push as event) ──
            if act_type == "mode":
                self.client.push_interaction_event(f"mode.{attrs.get('name', 'unknown')}")
                return "SUCCESS_MODE"

            # ── Unknown action type → safely ignore ──
            logger.warning("Router: Unknown action type '%s' — safely ignored.", act_type)
            return "IGNORED_UNKNOWN_ACTION"

        except Exception as e:
            logger.error("Router exception for '%s': %s", act_type, e)
            return f"ERROR_EXCEPTION_{act_type}_{e}"
