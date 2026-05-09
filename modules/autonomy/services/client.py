import requests
import logging
from datetime import datetime
import time

from modules.arduino_serial.contract import (
    SERVO_INDEX_PAN,
    SERVO_INDEX_TILT,
    build_buzzer_cmd,
    build_laser_cmd,
    build_lcd_cmd,
    build_set_servo_cmd,
    build_simple_cmd,
    build_sound_play_cmd,
    build_stepper_cmd,
)

logger = logging.getLogger("autonomy.client")

_ROBOT_COMMANDS = {"stand", "sit", "home", "zero_now", "estop", "calibrate", "get_state"}
_SENSOR_COMMANDS = {"ultra_read", "imu_read", "rfid_last"}

class ServiceClient:
    def __init__(self, base_urls, config=None):
        self.urls = base_urls
        cfg = config or {}
        self.speech_quiet_cfg = dict(cfg.get("speech_quiet_hours", {}))
        self.offline_cfg = dict(cfg.get("offline_mode", {}))
        self.request_timeouts = dict(cfg.get("request_timeouts", {}))
        self._availability_cache = {}

    def _post(self, service, endpoint, json=None, params=None, timeout_s=None):
        url = self.urls.get(service)
        if not url:
            return None
        try:
            full_url = f"{url}{endpoint}"
            timeout = float(timeout_s) if timeout_s is not None else float(self.request_timeouts.get("default_post_s", 1.0))
            resp = requests.post(full_url, json=json, params=params, timeout=timeout)
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            logger.debug(f"Failed to post to {service}: {e}")
            return None

    def _get(self, service, endpoint, params=None, timeout_s=None):
        url = self.urls.get(service)
        if not url:
            return None
        try:
            full_url = f"{url}{endpoint}"
            timeout = float(timeout_s) if timeout_s is not None else float(self.request_timeouts.get("default_get_s", 1.0))
            resp = requests.get(full_url, params=params, timeout=timeout)
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            logger.debug(f"Failed to get from {service}: {e}")
            return None

    def _get_vlm(self, endpoint, params=None):
        # MARK: Prefer new vlm endpoint, keep legacy vision fallback for compatibility.
        data = self._get("vlm", endpoint, params=params)
        if data is None:
            data = self._get("vision", endpoint, params=params)
        return data

    def _arduino_request(self, payload, timeout=1.0):
        data = self._post("arduino", "/request", json=payload, params={"timeout": float(timeout)})
        if not data:
            return None
        if isinstance(data, dict) and "resp" in data:
            return data.get("resp")
        return data

    def move_head(self, pan, tilt, speed=0.8):
        # Firmware expects per-servo writes: index 0=pan, 1=tilt.
        pan_resp = self._arduino_request(build_set_servo_cmd(SERVO_INDEX_PAN, int(pan)))
        tilt_resp = self._arduino_request(build_set_servo_cmd(SERVO_INDEX_TILT, int(tilt)))
        return {"ok": bool((pan_resp or {}).get("ok", False)) and bool((tilt_resp or {}).get("ok", False)), "pan": pan_resp, "tilt": tilt_resp}

    def set_laser(self, on: bool, id: int = 1, both: bool = False):
        return self._arduino_request(build_laser_cmd(on=on, id_=id, both=both))

    def set_buzzer(self, out: str = "loud", freq: int = 2200, ms: int = 60):
        return self._arduino_request(build_buzzer_cmd(out=out, freq=freq, ms=ms))

    def play_sound(self, name: str, out: str = "loud"):
        return self._arduino_request(build_sound_play_cmd(name=name, out=out))

    def set_lcd(self, msg: str = None, top: str = None, bottom: str = None, id: int = 0):
        payload = build_lcd_cmd(id_=id, msg=msg, top=top, bottom=bottom)
        return self._arduino_request(payload)

    def set_stepper(self, id: int, mode: str, value: int, drive: int = 200):
        return self._arduino_request(build_stepper_cmd(id_=id, mode=mode, value=value, drive=drive))

    def robot_command(self, cmd: str):
        """Send simple commands like 'stand', 'sit', 'home', 'zero_now'"""
        cmd_norm = str(cmd or "").strip().lower()
        if cmd_norm not in _ROBOT_COMMANDS:
            logger.debug("Unsupported robot_command requested: %s", cmd)
            return None
        return self._arduino_request(build_simple_cmd(cmd_norm))

    def read_sensor(self, type: str):
        """Request sensor data: 'ultra_read', 'imu_read', 'rfid_last'"""
        cmd_norm = str(type or "").strip().lower()
        if cmd_norm not in _SENSOR_COMMANDS:
            logger.debug("Unsupported sensor command requested: %s", type)
            return None
        return self._arduino_request(build_simple_cmd(cmd_norm))

    def system_control(self, service: str, action: str):
        """Send system commands like 'start' or 'stop' to a module"""
        svc = str(service or "").strip().lower()
        act = str(action or "").strip().lower()

        # Route service-specific control paths first
        route_map = {
            "speech": {"start": "/speech/start", "stop": "/speech/stop"},
            "wakeword": {"start": "/wakeword/start", "stop": "/wakeword/stop"},
            "autonomy": {"start": "/start", "stop": "/stop"},
            "notifier": {"start": "/start", "stop": "/stop"},
        }
        endpoint = route_map.get(svc, {}).get(act)
        if endpoint:
            return self._post(svc, endpoint)

        # Fallback generic
        return self._post(svc, f"/{act}")

    def arduino_send(self, payload: dict):
        return self._post("arduino", "/send", payload)

    def set_neopixel(self, effect, emotions=None, color=None, duration=None):
        payload = {"name": effect}
        if emotions:
            payload["emotions"] = emotions
        if color and len(color) == 3:
            payload["r"], payload["g"], payload["b"] = color
        if duration is not None:
            payload["duration"] = duration
        return self._post("neopixel", "/animate", json=payload)

    def set_neopixel_segment_effect(self, segment: str, effect: str, color=None, emotions=None, iterations=None):
        payload = {"name": effect, "segment": str(segment)}
        if emotions:
            payload["emotions"] = emotions
        if color and len(color) == 3:
            payload["r"], payload["g"], payload["b"] = color
        if iterations is not None:
            payload["iterations"] = int(iterations)
        return self._post("neopixel", "/animate", payload)

    def fill_neopixel_segment_color(self, segment: str, r: int, g: int, b: int):
        url = self.urls.get("neopixel")
        if not url:
            return None
        try:
            requests.post(
                f"{url}/fill",
                params={"r_": int(r), "g": int(g), "b": int(b), "segment": str(segment)},
                timeout=1.0,
            )
            return {"ok": True}
        except Exception as exc:
            logger.debug(f"Failed to fill neopixel segment color: {exc}")
            return None

    def apply_neopixel_preset(self, name: str):
        url = self.urls.get("neopixel")
        if not url:
            return None
        try:
            resp = requests.post(f"{url}/preset/apply", params={"name": str(name)}, timeout=1.0)
            return resp.json() if resp.status_code == 200 else None
        except Exception as exc:
            logger.debug(f"Failed to apply neopixel preset: {exc}")
            return None

    def fill_neopixel_color(self, r: int, g: int, b: int):
        url = self.urls.get("neopixel")
        if not url:
            return None
        try:
            requests.post(
                f"{url}/fill",
                params={"r_": int(r), "g": int(g), "b": int(b)},
                timeout=1.0,
            )
        except Exception as exc:
            logger.debug(f"Failed to fill neopixel color: {exc}")

    @staticmethod
    def _parse_hhmm(value):
        text = str(value or "").strip()
        parts = text.split(":")
        if len(parts) != 2:
            return None
        try:
            hh = int(parts[0])
            mm = int(parts[1])
        except Exception:
            return None
        if hh < 0 or hh > 23 or mm < 0 or mm > 59:
            return None
        return hh, mm

    def _quiet_hours_active(self):
        cfg = self.speech_quiet_cfg
        if not bool(cfg.get("enabled", False)):
            return False
        start = self._parse_hhmm(cfg.get("start", "23:00"))
        end = self._parse_hhmm(cfg.get("end", "07:00"))
        if start is None or end is None:
            return False
        now_dt = datetime.now()
        now = now_dt.hour * 60 + now_dt.minute
        start_m = start[0] * 60 + start[1]
        end_m = end[0] * 60 + end[1]
        if start_m == end_m:
            return True
        if start_m < end_m:
            return start_m <= now < end_m
        return now >= start_m or now < end_m

    def speak(self, text, tone=None, engine=None, language=None):
        text_value = str(text or "")
        if self._quiet_hours_active():
            max_chars = int(self.speech_quiet_cfg.get("max_chars", 120))
            prefix = str(self.speech_quiet_cfg.get("prefix", "")).strip()
            if max_chars > 0 and len(text_value) > max_chars:
                text_value = text_value[: max_chars - 3].rstrip() + "..."
            if prefix:
                text_value = f"{prefix}{text_value}"
            if tone is None:
                tone = self.speech_quiet_cfg.get("tone", "calm")
        payload = {"text": text}
        payload["text"] = text_value
        if tone:
            payload["tone"] = tone
        if engine:
            payload["engine"] = engine
        if language:
            payload["language"] = str(language)
        return self._post("speak", "/say", payload)

    def chat(self, query, apply_actions: bool = False, source_lang: str | None = None, response_lang: str | None = None):
        params = {"query": query, "apply_actions": str(bool(apply_actions)).lower()}
        if source_lang:
            params["source_lang"] = str(source_lang)
        if response_lang:
            params["response_lang"] = str(response_lang)
        timeout = float(self.request_timeouts.get("ollama_chat_s", 20.0))
        return self._post("ollama", "/chat", None, params=params, timeout_s=timeout)

    def warmup_ollama(self):
        timeout = float(self.request_timeouts.get("ollama_warmup_s", 2.5))
        return self._post("ollama", "/warmup", timeout_s=timeout)

    def get_speech_direction(self):
        return self._get("speech", "/direction")

    def get_last_speech(self):
        return self._get("speech", "/last")

    def push_interaction_event(self, event_type, data=None):
        return self._post("interactions", "/event", {"type": event_type, "data": data})

    def set_interaction_effect(self, name: str, duration_ms: int = 800, force: bool = False):
        payload = {"name": str(name), "duration_ms": int(duration_ms), "force": bool(force)}
        return self._post("interactions", "/effect", payload)

    def set_interaction_base(self, name: str, color=None):
        payload = {"name": str(name)}
        if color is not None:
            payload["color"] = color
        return self._post("interactions", "/base", payload)

    def set_speech_tracking(self, enabled):
        endpoint = "/track/start" if enabled else "/track/stop"
        return self._post("speech", endpoint)

    def translate(self, text, source_lang: str, target_lang: str):
        params = {
            "text": str(text or ""),
            "source_lang": str(source_lang or "auto"),
            "target_lang": str(target_lang or "en"),
        }
        return self._post("ollama", "/translate", None, params=params)

    def select_persona(self, name):
        return self._post("ollama", "/persona/select", {"name": name})

    def update_emotions(self, emotions):
        if not emotions:
            return None
        payload = {"values": emotions}
        return self._post("state_manager", "/set/emotions", payload)

    def run_animation(self, name, speed=1.0, loop=False):
        url = self.urls.get("animate")
        if not url:
            return None
        try:
            full_url = f"{url}/run"
            resp = requests.post(full_url, params={"name": name, "speed": speed, "loop": loop}, timeout=1.0)
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            logger.debug(f"Failed to trigger animation {name}: {e}")
            return None

    def is_service_available(self, service: str) -> bool:
        svc = str(service or "").strip().lower()
        if not svc:
            return False
        ttl = float(self.offline_cfg.get("availability_ttl_s", 5.0))
        now = time.time()
        cached = self._availability_cache.get(svc)
        if isinstance(cached, tuple) and len(cached) == 2:
            ts, ok = cached
            if now - float(ts) <= ttl:
                return bool(ok)

        url = self.urls.get(svc)
        if not url:
            self._availability_cache[svc] = (now, False)
            return False

        endpoint = "/status" if svc == "speak" else "/healthz"
        try:
            resp = requests.get(f"{url}{endpoint}", timeout=0.6)
            ok = resp.status_code == 200
        except Exception:
            ok = False
        self._availability_cache[svc] = (now, ok)
        return ok

    def oled_show(self, name: str):
        return self._post("oled_faces", "/manual", {"mode": "bitmap", "name": str(name)})

    def oled_anim(self, name: str):
        return self._post("oled_faces", "/manual", {"mode": "animation", "name": str(name)})

    def oled_stop(self):
        return self._post("oled_faces", "/manual", {"mode": "bitmap", "name": "normal"})

    def oled_logo(self):
        return self._post("oled_faces", "/manual", {"mode": "logo", "name": "logo"})

    def get_latest_vision_results(self, limit=5):
        data = self._get_vlm("/results/latest", params={"limit": limit})
        if not data:
            return []
        return data.get("results", [])

    def get_person_memory(self, person):
        if not person:
            return None
        return self._get_vlm("/memory/person", params={"person": person})

    def list_people_memory(self):
        data = self._get_vlm("/memory/people")
        if not data:
            return []
        return data.get("people", [])

    def append_person_chat(self, person: str, text: str, role: str = "assistant"):
        if not person or not text:
            return None
        params = {
            "person": str(person),
            "text": str(text),
            "role": str(role or "assistant"),
        }
        return self._post("vlm", "/memory/chat", params=params)

    def start_face_follow(self, person: str | None = None):
        params = {"person": str(person)} if person else None
        return self._post("vlm", "/follow/start", params=params)

    def stop_face_follow(self):
        return self._post("vlm", "/follow/stop")

    def get_face_follow_status(self):
        return self._get_vlm("/follow/status")

    # ── Living Vision Agent Methods ──

    def get_visual_context(self):
        return self._get_vlm("/context/latest")

    def refresh_visual_context(self):
        return self._post("vlm", "/context/refresh")

    def focus_person(self, person: str):
        if not person:
            return None
        return self._post("vlm", "/focus/person", params={"person": str(person)})

    def start_owner_follow(self):
        return self._post("vlm", "/follow/owner/start")

    def check_rfid(self, endpoint):
        if not endpoint:
            return False
        try:
            resp = requests.get(endpoint, timeout=1.0)
            if resp.status_code != 200:
                return False
            data = resp.json()
            if isinstance(data, dict):
                return bool(data.get("authorized") or data.get("ok"))
            return bool(data)
        except Exception as exc:
            logger.debug("RFID check failed: %s", exc)
            return False

    def queue_action(self, action_type: str, priority: int = 50, ttl_ms: int = 5000, payload: dict = None):
        if payload is None:
            payload = {}
        # Try routing through agent core endpoint (assuming gateway exposes it at /agent)
        url = self.urls.get("agent_core") or "http://127.0.0.1:8080/agent"
        try:
            resp = requests.post(f"{url}/actions/queue", json={
                "type": action_type,
                "priority": priority,
                "ttl_ms": ttl_ms,
                "payload": payload,
            }, timeout=1.0)
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            logger.debug(f"Failed to queue action {action_type}: {e}")
            return None

    def emit_agent_event(self, event_type: str, payload: dict | None = None):
        if payload is None:
            payload = {}
        url = self.urls.get("agent_core") or "http://127.0.0.1:8080/agent"
        try:
            resp = requests.post(
                f"{url}/events",
                json={"type": str(event_type), "payload": payload},
                timeout=1.0,
            )
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            logger.debug(f"Failed to emit agent event {event_type}: {e}")
            return None
