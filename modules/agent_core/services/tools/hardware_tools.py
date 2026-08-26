from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Sequence

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

    def print_to_lcd(self, top: str, bottom: str) -> str:
        if not self.client:
            return "Error: Hardware client disconnected."
        try:
            from modules.arduino_serial.contract import build_lcd_cmd

            self.client._arduino_request(build_lcd_cmd(top=top, bottom=bottom))
            return f"Printed to LCD: '{top}' / '{bottom}'"
        except Exception as e:
            return f"Failed to print to LCD: {e}"

    def get_last_rfid(self) -> str:
        if not self.client:
            return "Error: Hardware client disconnected."
        try:
            from modules.arduino_serial.contract import build_simple_cmd

            resp = self.client._arduino_request(build_simple_cmd("rfid_last"))
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
        """Submit an action to the action arbiter."""
        if payload is None:
            payload = {}
        try:
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
            if data.get("ok") is True:
                action_id = data.get("action_id", "unknown")
                return f"Action queued: {action_id}"
            reason = data.get("reason") or data.get("error") or data.get("message") or "unknown"
            return f"Queue action rejected: {reason}"
        except Exception as exc:
            return f"Queue action failed: {exc}"

    def get_action_status(self) -> str:
        try:
            resp = self._http.get("agent/actions/status", timeout=2.0)
            if resp.status_code == 200:
                return str(resp.json())
            return f"Action status failed: HTTP {resp.status_code}"
        except Exception as exc:
            return f"Action status failed: {exc}"

    def cancel_action(self, action_id: str) -> str:
        try:
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
