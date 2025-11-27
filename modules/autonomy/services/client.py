import requests
import logging

logger = logging.getLogger("autonomy.client")

class ServiceClient:
    def __init__(self, base_urls):
        self.urls = base_urls

    def _post(self, service, endpoint, json=None):
        url = self.urls.get(service)
        if not url:
            return None
        try:
            full_url = f"{url}{endpoint}"
            resp = requests.post(full_url, json=json, timeout=1.0)
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            logger.debug(f"Failed to post to {service}: {e}")
            return None

    def _get(self, service, endpoint):
        url = self.urls.get(service)
        if not url:
            return None
        try:
            full_url = f"{url}{endpoint}"
            resp = requests.get(full_url, timeout=1.0)
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            logger.debug(f"Failed to get from {service}: {e}")
            return None

    def move_head(self, pan, tilt):
        return self._post("arduino", "/send", {"cmd": "set_servo", "pan": pan, "tilt": tilt})

    def set_neopixel(self, effect, emotions=None):
        url = self.urls.get("neopixel")
        if not url:
            return None
        try:
            # Construct query string
            q = f"?name={effect}"
            if emotions:
                for e in emotions:
                    q += f"&emotions={e}"
            
            full_url = f"{url}/animate{q}"
            requests.post(full_url, timeout=1.0)
        except Exception:
            pass

    def speak(self, text):
        return self._post("speak", "/say", {"text": text})

    def chat(self, query):
        return self._post("ollama", "/chat", {"query": query}) # Changed to POST as per likely API

    def get_speech_direction(self):
        return self._get("speech", "/direction")

    def get_last_speech(self):
        return self._get("speech", "/last")
    def push_interaction_event(self, event_type, data=None):
        return self._post("interactions", "/event", {"type": event_type, "data": data})

    def set_speech_tracking(self, enabled):
        endpoint = "/track/start" if enabled else "/track/stop"
        return self._post("speech", endpoint)

    def chat_rag(self, query):
        return self._post("wiki_rag", "/chat", {"query": query})

    def select_persona(self, name):
        return self._post("ollama", "/persona/select", {"name": name})
