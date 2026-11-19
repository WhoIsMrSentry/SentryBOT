from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("agent.tools.hardware")


_COLOR_NAME_MAP: Dict[str, List[int]] = {
    "black": [0, 0, 0],
    "off": [0, 0, 0],
    "white": [255, 255, 255],
    "red": [255, 0, 0],
    "green": [0, 255, 0],
    "blue": [0, 0, 255],
    "yellow": [255, 255, 0],
    "orange": [255, 128, 0],
    "purple": [128, 0, 255],
    "pink": [255, 64, 128],
    "cyan": [0, 255, 255],
    "teal": [0, 128, 128],
    "magenta": [255, 0, 255],
    "warm": [255, 160, 80],
    "calm": [60, 120, 255],
    "kırmızı": [255, 0, 0],
    "kirmizi": [255, 0, 0],
    "yeşil": [0, 255, 0],
    "yesil": [0, 255, 0],
    "mavi": [0, 0, 255],
    "sarı": [255, 255, 0],
    "sari": [255, 255, 0],
    "turuncu": [255, 128, 0],
    "mor": [128, 0, 255],
    "pembe": [255, 64, 128],
    "beyaz": [255, 255, 255],
    "siyah": [0, 0, 0],
    "kapali": [0, 0, 0],
    "kapalı": [0, 0, 0],
}


def _clamp_rgb_channel(value: Any) -> int:
    try:
        return max(0, min(255, int(value)))
    except Exception:
        return 0


def _normalize_rgb(color: Any) -> Optional[List[int]]:
    """Accept RGB arrays/tuples or common color names and return [r, g, b]."""
    if color is None or color == "":
        return None
    if isinstance(color, str):
        key = color.strip().lower().replace(" ", "_").replace("-", "_")
        if key.startswith("#") and len(key) == 7:
            try:
                return [int(key[1:3], 16), int(key[3:5], 16), int(key[5:7], 16)]
            except Exception:
                return None
        return list(_COLOR_NAME_MAP.get(key, [0, 0, 0]))
    if isinstance(color, Sequence) and not isinstance(color, (bytes, bytearray, str)):
        vals = list(color)[:3]
        while len(vals) < 3:
            vals.append(0)
        return [_clamp_rgb_channel(vals[0]), _clamp_rgb_channel(vals[1]), _clamp_rgb_channel(vals[2])]
    return None


class HardwareToolsMixin:
    """Hardware and system tools for ToolRegistry.

    LLM-facing physical actions must not write hardware directly when an
    arbiter/action path exists. This mixin keeps compatibility methods but
    routes shared outputs through the action arbiter where possible.
    """

    def play_sound(self, name: str) -> str:
        if not self.client:
            return "Error: Hardware client disconnected."
        resp = self.client.play_sound(name)
        return f"Playing sound: {name}. Response: {resp}"

    def set_lights(self, effect: str, color: Any = None) -> str:
        """Queue a light action through ActionArbiter instead of direct LED writes."""
        effect_name = str(effect or "BREATHE").strip().upper()
        if effect_name not in {
            "COMET",
            "PULSE",
            "WAVE",
            "SOLID",
            "OFF",
            "BREATHE",
            "RANDOM_BLINK",
            "TWINKLE",
        }:
            effect_name = "BREATHE"
        rgb = _normalize_rgb(color)
        if effect_name == "OFF":
            rgb = [0, 0, 0]
        payload: Dict[str, Any] = {"effect": effect_name}
        if rgb is not None:
            payload["color"] = rgb
        result = self.queue_action(
            "lights",
            priority=60,
            ttl_ms=3000,
            payload=payload,
        )
        if result.startswith("Action queued"):
            return f"Lights queued: {effect_name} RGB={rgb if rgb is not None else 'default'}"
        return result

    def _send_arduino_request(self, payload: Dict[str, Any], timeout: float = 1.0) -> Any:
        public_fn = getattr(self.client, "arduino_request", None) if self.client is not None else None
        if callable(public_fn):
            return public_fn(payload, timeout=timeout)
        return self._http.arduino_request(payload, timeout=timeout)

    def print_to_lcd(self, top: str, bottom: str) -> str:
        if not self.client:
            return "Error: Hardware client disconnected."
        try:
            from modules.arduino_serial.contract import build_lcd_cmd

            self._send_arduino_request(build_lcd_cmd(top=top, bottom=bottom))
            return f"Printed to LCD: '{top}' / '{bottom}'"
        except Exception as e:
            return f"Failed to print to LCD: {e}"

    def get_last_rfid(self) -> str:
        if not self.client:
            return "Error: Hardware client disconnected."
        try:
            from modules.arduino_serial.contract import build_simple_cmd

            resp = self._send_arduino_request(build_simple_cmd("rfid_last"))
            if isinstance(resp, dict) and resp.get("ok"):
                return f"Last RFID: {resp.get('rfid', 'None')}"
            return f"Last RFID Response: {resp}"
        except Exception as e:
            return f"Failed to get RFID: {e}"

    def get_sensor_data(self) -> str:
        bat = self.world_state.get_state().get("battery_percent", "unknown")
        dist_info = "Distance unknown"
        if self.client:
            ultra = self.client.read_sensor("ultra_read")
            if ultra and "cm" in str(ultra):
                dist_info = f"Obstacle at {ultra}"
        return f"Battery: {bat}%. {dist_info}"

    def queue_action(
        self,
        action_type: str,
        priority: int = 50,
        ttl_ms: int = 5000,
        payload: dict = None,
    ) -> str:
        """Submit an action to the action arbiter (in-process when bound, HTTP fallback)."""
        if payload is None:
            payload = {}
        try:
            arbiter = getattr(self, "action_arbiter", None)
            if arbiter is not None:
                from modules.agent_core.services.action_arbiter import ActionRequest

                data = arbiter.submit(
                    ActionRequest(
                        type=str(action_type or "").strip(),
                        source="agent_core",
                        priority=int(priority),
                        ttl_ms=int(ttl_ms),
                        payload=dict(payload),
                    )
                )
            else:
                resp = self._http.post(
                    "agent/actions/queue",
                    json_data={
                        "type": action_type,
                        "priority": priority,
                        "ttl_ms": ttl_ms,
                        "payload": payload,
                        "source": "agent_core",
                    },
                    timeout=2.0,
                )
                if resp.status_code != 200:
                    return f"Queue action failed: HTTP {resp.status_code}"
                try:
                    data = resp.json()
                except Exception:
                    return "Queue action failed: invalid JSON response"
            if isinstance(data, dict) and data.get("ok") is True:
                action_id = data.get("action_id", "unknown")
                return f"Action queued: {action_id}"
            reason = (
                (data.get("reason") or data.get("error") or data.get("message") or "unknown")
                if isinstance(data, dict)
                else "unknown"
            )
            return f"Queue action rejected: {reason}"
        except Exception as exc:
            return f"Queue action failed: {exc}"

    def get_action_status(self) -> str:
        try:
            arbiter = getattr(self, "action_arbiter", None)
            if arbiter is not None:
                return str({"ok": True, "exclusive_locks": arbiter.get_exclusive_status()})
            resp = self._http.get("agent/actions/status", timeout=2.0)
            if resp.status_code == 200:
                return str(resp.json())
            return f"Action status failed: HTTP {resp.status_code}"
        except Exception as exc:
            return f"Action status failed: {exc}"

    def cancel_action(self, action_id: str) -> str:
        try:
            arbiter = getattr(self, "action_arbiter", None)
            if arbiter is not None:
                ok = bool(arbiter.cancel(str(action_id)))
                return str({"ok": ok, "action_id": str(action_id)})
            resp = self._http.post(
                "agent/actions/cancel",
                json_data={"action_id": str(action_id)},
                timeout=2.0,
            )
            if resp.status_code == 200:
                return str(resp.json())
            return f"Cancel action failed: HTTP {resp.status_code}"
        except Exception as exc:
            return f"Cancel action failed: {exc}"

    def robot_posture(self, posture: str) -> str:
        """Change physical leg posture (stand/sit/home/estop) via arbiter or Arduino contract."""
        pos = str(posture or "").strip().lower()
        if pos not in {"stand", "sit", "home", "estop"}:
            return f"Error: invalid posture '{posture}'."
        if getattr(self, "action_arbiter", None) is not None:
            return self.queue_action("legs_posture", priority=75 if pos == "estop" else 60, payload={"posture": pos})
        if not self.client and self._http is None:
            return "Error: Hardware client disconnected."
        from modules.arduino_serial.contract import build_simple_cmd

        resp = self._send_arduino_request(build_simple_cmd(pos), timeout=1.5)
        return f"Posture '{pos}' executed. Response: {resp}"

    def move_body(self, direction: str, speed: int = 60, steps: int = 200) -> str:
        """Drive or turn robot body safely via SafetyFilter and ActionArbiter."""
        dir_norm = str(direction or "").strip().lower()
        if dir_norm not in {"forward", "backward", "left", "right", "stop"}:
            return f"Error: invalid direction '{direction}'."
        safe_speed = abs(self.safety.clamp_stepper(int(speed or 0))) if hasattr(self, "safety") else int(speed or 60)
        safe_steps = max(20, min(2000, int(steps or 200)))
        if getattr(self, "action_arbiter", None) is not None:
            return self.queue_action(
                "legs_move",
                priority=80 if dir_norm == "stop" else 60,
                payload={"direction": dir_norm, "speed": safe_speed, "steps": safe_steps},
            )
        from modules.arduino_serial.contract import build_drive_cmd, build_simple_cmd, build_stepper_cmd

        if dir_norm == "stop":
            resp = self._send_arduino_request(build_simple_cmd("estop"))
            return f"Emergency stop executed. Response: {resp}"
        if dir_norm in {"forward", "backward"}:
            val = safe_speed if dir_norm == "forward" else -safe_speed
            resp = self._send_arduino_request(build_drive_cmd(val))
            return f"Drive '{dir_norm}' speed={safe_speed}. Response: {resp}"
        sign = 1 if dir_norm == "right" else -1
        r0 = self._send_arduino_request(build_stepper_cmd(0, "pos", sign * safe_steps, drive=safe_speed))
        r1 = self._send_arduino_request(build_stepper_cmd(1, "pos", -sign * safe_steps, drive=safe_speed))
        return f"Turn '{dir_norm}' steps={safe_steps} speed={safe_speed}. Response: {r0}/{r1}"

    def control_laser(self, state: str, target: str = "both", duration_s: float = 2.0) -> str:
        """Turn pointer laser(s) on/off with SafetyFilter duration limit."""
        st = str(state or "off").strip().lower()
        tgt = str(target or "both").strip().lower()
        if st not in {"on", "off"}:
            return f"Error: invalid laser state '{state}'."
        if tgt not in {"both", "left", "right"}:
            tgt = "both"
        dur = self.safety.clamp_laser_duration(float(duration_s or 2.0)) if hasattr(self, "safety") else min(2.0, float(duration_s or 2.0))
        if getattr(self, "action_arbiter", None) is not None:
            return self.queue_action(
                "laser",
                priority=60,
                ttl_ms=int(dur * 1000) + 1000,
                payload={"on": st == "on", "target": tgt, "duration_s": dur},
            )
        from modules.arduino_serial.contract import build_laser_cmd

        if st == "off":
            resp = self._send_arduino_request(build_laser_cmd(on=False, both=True))
            return f"Lasers turned off. Response: {resp}"
        cmd = (
            build_laser_cmd(on=True, id_=1)
            if tgt == "left"
            else build_laser_cmd(on=True, id_=2)
            if tgt == "right"
            else build_laser_cmd(on=True, both=True)
        )
        resp = self._send_arduino_request(cmd)
        return f"Laser {tgt} turned on (duration<={dur:.1f}s). Response: {resp}"

    def move_ears(self, left: Optional[int] = None, right: Optional[int] = None, gesture: str = "") -> str:
        """Control Pi GPIO ear servos via angles or preset gesture."""
        gest = str(gesture or "").strip().lower()
        if getattr(self, "action_arbiter", None) is not None:
            payload: Dict[str, Any] = {}
            if gest:
                payload["gesture"] = gest
            if left is not None:
                payload["left"] = self.safety.clamp_servo(left) if hasattr(self, "safety") else int(left)
            if right is not None:
                payload["right"] = self.safety.clamp_servo(right) if hasattr(self, "safety") else int(right)
            return self.queue_action("ears", priority=55, payload=payload)
        try:
            if gest:
                resp = self._http.post("piservo/gesture", params={"name": gest}, timeout=1.5)
                return f"Ear gesture '{gest}' status={resp.status_code}"
            l_val = self.safety.clamp_servo(90 if left is None else left) if hasattr(self, "safety") else int(90 if left is None else left)
            r_val = self.safety.clamp_servo(90 if right is None else right) if hasattr(self, "safety") else int(90 if right is None else right)
            resp = self._http.post("piservo/set", params={"left": l_val, "right": r_val}, timeout=1.5)
            return f"Ears moved to left={l_val}, right={r_val} status={resp.status_code}"
        except Exception as exc:
            return f"Failed to move ears: {exc}"

    def play_buzzer(self, frequency: int = 2200, duration_ms: int = 80, cute_sound: str = "") -> str:
        """Play a hardware buzzer tone or named cute sound via Arduino contract."""
        cute = str(cute_sound or "").strip()
        freq = max(100, min(10000, int(frequency or 2200)))
        ms = max(10, min(2000, int(duration_ms or 80)))
        if getattr(self, "action_arbiter", None) is not None:
            return self.queue_action(
                "audio_hw",
                priority=55,
                payload={"cute_sound": cute, "frequency": freq, "duration_ms": ms},
            )
        from modules.arduino_serial.contract import build_buzzer_cmd, build_cute_cmd

        cmd = build_cute_cmd(cute) if cute else build_buzzer_cmd(freq=freq, ms=ms)
        resp = self._send_arduino_request(cmd)
        return f"Audio hardware triggered ({cute or f'{freq}Hz/{ms}ms'}). Response: {resp}"
