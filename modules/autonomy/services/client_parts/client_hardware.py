from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from modules.arduino_serial.contract import (
    SERVO_INDEX_PAN,
    SERVO_INDEX_TILT,
    build_buzzer_cmd,
    build_lcd_cmd,
    build_liveliness_cmd,
    build_set_servo_cmd,
    build_simple_cmd,
    build_sound_play_cmd,
    build_stepper_cmd,
)
from .client_lights import ClientLightsMixin

logger = logging.getLogger("autonomy.client")

_ROBOT_COMMANDS = {"stand", "sit", "home", "zero_now", "estop", "calibrate", "get_state"}
_SENSOR_COMMANDS = {"ultra_read", "imu_read", "rfid_last"}


class ClientHardwareMixin(ClientLightsMixin):
    """Hardware, Arduino, NeoPixel, and OLED control methods for ServiceClient."""

    urls: Dict[str, str]
    head_arbiter: Any
    request_timeouts: Dict[str, Any]
    _post: Callable[..., Any]
    _get: Callable[..., Any]
    _arduino_request: Callable[..., Any]
    _async_post: Callable[..., Any]
    _async_get: Callable[..., Any]

    def move_head(self, pan: float, tilt: float, speed: float = 0.8, source: str = "autonomy", priority: int = 30) -> Dict[str, Any]:
        if self.head_arbiter is not None and hasattr(self.head_arbiter, "move"):
            try:
                res = self.head_arbiter.move(pan=float(pan), tilt=float(tilt), source=source, priority=int(priority))
                if res and res.get("ok"):
                    return res
                # Denied by priority policy: respect the decision. A denial
                # must never fall through to a raw servo write (R2).
                logger.debug("head move denied by arbiter (%s): pan=%s tilt=%s", (res or {}).get("reason"), pan, tilt)
                return {
                    "ok": False,
                    "reason": "arbiter_denied",
                    "detail": res,
                    "pan": float(pan),
                    "tilt": float(tilt),
                }
            except Exception as exc:
                # Arbiter itself is broken (not a policy denial) — degrade.
                logger.debug("direct head_arbiter move failed in autonomy client: %s", exc)

        pan_resp = self._arduino_request(build_set_servo_cmd(SERVO_INDEX_PAN, int(pan)))
        tilt_resp = self._arduino_request(build_set_servo_cmd(SERVO_INDEX_TILT, int(tilt)))
        return {
            "ok": bool((pan_resp or {}).get("ok", False)) and bool((tilt_resp or {}).get("ok", False)),
            "pan": pan_resp,
            "tilt": tilt_resp,
        }

    def set_liveliness(self, enable: bool, mode: str = "breathe", amplitude_deg=None, period_ms=None, pan_center=None, tilt_center=None) -> Any:
        return self._arduino_request(
            build_liveliness_cmd(
                bool(enable),
                mode=mode,
                amplitude_deg=amplitude_deg,
                period_ms=period_ms,
                pan_center=pan_center,
                tilt_center=tilt_center,
            )
        )

    def set_buzzer(self, out: str = "loud", freq: int = 2200, ms: int = 60) -> Any:
        return self._arduino_request(build_buzzer_cmd(out=out, freq=freq, ms=ms))

    def play_sound(self, name: str, out: str = "loud") -> Any:
        return self._arduino_request(build_sound_play_cmd(name=name, out=out))

    def set_lcd(self, msg: str = None, top: str = None, bottom: str = None, id: int = 0) -> Any:
        payload = build_lcd_cmd(id_=id, msg=msg, top=top, bottom=bottom)
        return self._arduino_request(payload)

    def set_stepper(self, id: int, mode: str, value: int, drive: int = 200) -> Any:
        return self._arduino_request(build_stepper_cmd(id_=id, mode=mode, value=value, drive=drive))

    def robot_command(self, cmd: str) -> Any:
        cmd_norm = str(cmd or "").strip().lower()
        if cmd_norm not in _ROBOT_COMMANDS:
            logger.debug("Unsupported robot_command requested: %s", cmd)
            return None
        return self._arduino_request(build_simple_cmd(cmd_norm))

    def read_sensor(self, type: str) -> Any:
        cmd_norm = str(type or "").strip().lower()
        if cmd_norm not in _SENSOR_COMMANDS:
            logger.debug("Unsupported sensor command requested: %s", type)
            return None
        return self._arduino_request(build_simple_cmd(cmd_norm))

    def system_control(self, service: str, action: str) -> Any:
        svc = str(service or "").strip().lower()
        act = str(action or "").strip().lower()
        route_map = {
            "speech": {"start": "/speech/start", "stop": "/speech/stop"},
            "wakeword": {"start": "/wakeword/start", "stop": "/wakeword/stop"},
            "autonomy": {"start": "/start", "stop": "/stop"},
            "notifier": {"start": "/start", "stop": "/stop"},
        }
        endpoint = route_map.get(svc, {}).get(act)
        if endpoint:
            return self._post(svc, endpoint)
        return self._post(svc, f"/{act}")

    def arduino_send(self, payload: dict) -> Any:
        return self._post("arduino", "/send", payload)

    def run_animation(self, name: str, speed: float = 1.0, loop: bool = False) -> Any:
        url = self.urls.get("animate")
        if not url:
            return None
        try:
            import requests
            full_url = f"{url}/run"
            resp = requests.post(full_url, params={"name": name, "speed": speed, "loop": loop}, timeout=1.0)
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            logger.debug("Failed to trigger animation %s: %s", name, e)
            return None

    async def async_move_head(self, pan: int, tilt: int, speed: float = 0.8) -> dict:
        pan_resp = await self._async_post(
            "arduino", "/request",
            json=build_set_servo_cmd(SERVO_INDEX_PAN, int(pan)),
            params={"timeout": 1.0}
        )
        tilt_resp = await self._async_post(
            "arduino", "/request",
            json=build_set_servo_cmd(SERVO_INDEX_TILT, int(tilt)),
            params={"timeout": 1.0}
        )
        return {
            "ok": bool((pan_resp or {}).get("ok", False)) and bool((tilt_resp or {}).get("ok", False)),
            "pan": pan_resp,
            "tilt": tilt_resp,
        }

    async def async_look_around(self) -> dict:
        steps = [(60, 90), (90, 90), (120, 90), (90, 90), (90, 70), (90, 110)]
        results = []
        import asyncio
        for pan, tilt in steps:
            res = await self.async_move_head(pan, tilt)
            results.append({"pan": pan, "tilt": tilt, "ok": res.get("ok", False)})
            await asyncio.sleep(0.6)
        return {"ok": all(r["ok"] for r in results), "steps": results}

    async def async_get_sensor_data(self) -> dict:
        try:
            url = self.urls.get("arduino", "")
            if not url:
                return {"error": "arduino url not configured"}
            from modules.common.http_client import get_http_client
            client = get_http_client(url, 2.0)
            resp = await client.post(
                "/emergency",
                json=build_simple_cmd("ultra_read"),
                timeout=2.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                return {"distance_cm": data.get("cm"), "raw": data}
        except Exception as e:
            logger.debug("async_get_sensor_data failed: %s", e)
        return {"distance_cm": None}

    async def async_animate(self, name: str, speed: float = 1.0, loop: bool = False) -> dict:
        return await self._async_post(
            "animate", "/run",
            params={"name": name, "speed": speed, "loop": str(bool(loop)).lower()},
            timeout=2.0,
        )
