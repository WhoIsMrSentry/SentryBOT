import requests
import logging

logger = logging.getLogger("autonomy.client")

class ServiceClient:
    def __init__(self, base_urls):
        self.urls = base_urls

    def _post(self, service, endpoint, json=None, params=None):
        url = self.urls.get(service)
        if not url:
            return None
        try:
            full_url = f"{url}{endpoint}"
            resp = requests.post(full_url, json=json, params=params, timeout=1.0)
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            logger.debug(f"Failed to post to {service}: {e}")
            return None

    def _get(self, service, endpoint, params=None):
        url = self.urls.get(service)
        if not url:
            return None
        try:
            full_url = f"{url}{endpoint}"
            resp = requests.get(full_url, params=params, timeout=1.0)
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            logger.debug(f"Failed to get from {service}: {e}")
            return None

    def move_head(self, pan, tilt, speed=0.8):
        return self._post("arduino", "/send", {"cmd": "set_servo", "pan": pan, "tilt": tilt, "speed": speed})

    def set_laser(self, on: bool, id: int = 1, both: bool = False):
        return self._post("arduino", "/send", {"cmd": "laser", "id": id, "on": on, "both": both})

    def set_buzzer(self, out: str = "loud", freq: int = 2200, ms: int = 60):
        return self._post("arduino", "/send", {"cmd": "buzzer", "out": out, "freq": freq, "ms": ms})

    def play_sound(self, name: str, out: str = "loud"):
        return self._post("arduino", "/send", {"cmd": "sound_play", "name": name, "out": out})

    def set_lcd(self, msg: str = None, top: str = None, bottom: str = None, id: int = 0):
        payload = {"cmd": "lcd", "id": id}
        if msg: payload["msg"] = msg
        if top: payload["top"] = top
        if bottom: payload["bottom"] = bottom
        return self._post("arduino", "/send", payload)

    def set_stepper(self, id: int, mode: str, value: int, drive: int = 200):
        return self._post("arduino", "/send", {"cmd": "stepper", "id": id, "mode": mode, "value": value, "drive": drive})

    def robot_command(self, cmd: str):
        """Send simple commands like 'stand', 'sit', 'home', 'zero_now'"""
        return self._post("arduino", "/send", {"cmd": cmd})

    def read_sensor(self, type: str):
        """Request sensor data: 'ultra_read', 'imu_read', 'rfid_last'"""
        return self._post("arduino", "/send", {"cmd": type})

    def system_control(self, service: str, action: str):
        """Send system commands like 'start' or 'stop' to a module"""
        # Mapping generic actions to service-specific endpoints if needed
        endpoint = f"/{action}"
        return self._post(service, endpoint)

    def set_neopixel(self, effect, emotions=None, color=None):
        params = {"name": effect}
        if emotions:
            params["emotions"] = emotions
        if color and len(color) == 3:
            params["r"], params["g"], params["b"] = color
        return self._post("neopixel", "/animate", params=params)

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

    def speak(self, text, tone=None, engine=None):
        payload = {"text": text}
        if tone:
            payload["tone"] = tone
        if engine:
            payload["engine"] = engine
        return self._post("speak", "/say", payload)

    def chat(self, query, apply_actions: bool = False):
        params = {"query": query, "apply_actions": str(bool(apply_actions)).lower()}
        return self._post("ollama", "/chat", None, params=params)

    def get_speech_direction(self):
        return self._get("speech", "/direction")

    def get_last_speech(self):
        return self._get("speech", "/last")

    def push_interaction_event(self, event_type, data=None):
        return self._post("interactions", "/event", {"type": event_type, "data": data})

    def set_speech_tracking(self, enabled):
        endpoint = "/track/start" if enabled else "/track/stop"
        return self._post("speech", endpoint)

    def chat_rag(self, query, apply_actions: bool = False):
        params = {"query": query, "apply_actions": str(bool(apply_actions)).lower()}
        return self._post("wiki_rag", "/chat", None, params=params)

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

    def get_latest_vision_results(self, limit=5):
        data = self._get("vision", "/results/latest", params={"limit": limit})
        if not data:
            return []
        return data.get("results", [])

    def get_person_memory(self, person):
        if not person:
            return None
        return self._get("vision", "/memory/person", params={"person": person})

    def list_people_memory(self):
        data = self._get("vision", "/memory/people")
        if not data:
            return []
        return data.get("people", [])

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
