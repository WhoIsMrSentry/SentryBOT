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
    build_liveliness_cmd,
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
        try:
            from modules.gateway.url import gateway_url, resolve_gateway_base_url, rewrite_loopback_urls

            base = resolve_gateway_base_url()
            self.urls = rewrite_loopback_urls(dict(base_urls or {}), base)
            self.urls.setdefault("agent_core", gateway_url(base, "/agent"))
        except Exception:
            self.urls = dict(base_urls or {})
        cfg = config or {}
        self.speech_quiet_cfg = dict(cfg.get("speech_quiet_hours", {}))
        self.offline_cfg = dict(cfg.get("offline_mode", {}))
        self.request_timeouts = dict(cfg.get("request_timeouts", {}))
        speech_cfg = cfg.get("speech", {}) if isinstance(cfg.get("speech"), dict) else {}
        self.speech_stream_cfg = dict(speech_cfg)
        self._availability_cache = {}

    def _agent_core_url(self) -> str:
        try:
            from modules.gateway.url import gateway_url, resolve_gateway_base_url

            return str(self.urls.get("agent_core") or gateway_url(resolve_gateway_base_url(), "/agent"))
        except Exception:
            return str(self.urls.get("agent_core") or "http://127.0.0.1:8080/agent")

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

    def set_liveliness(self, enable: bool, mode: str = "breathe", amplitude_deg=None, period_ms=None, pan_center=None, tilt_center=None):
        """Enable/disable firmware-native idle liveliness (breathing/micro-motion)."""
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

    @staticmethod
    def _parse_rgb(color) -> tuple[int, int, int] | None:
        if isinstance(color, (list, tuple)) and len(color) >= 3:
            try:
                return (int(color[0]) & 255, int(color[1]) & 255, int(color[2]) & 255)
            except (TypeError, ValueError):
                return None
        if isinstance(color, str):
            s = color.strip()
            if s.startswith("#") and len(s) >= 7:
                try:
                    v = int(s[1:7], 16)
                    return ((v >> 16) & 255, (v >> 8) & 255, v & 255)
                except ValueError:
                    return None
            if "," in s:
                parts = [p.strip() for p in s.split(",")]
                if len(parts) >= 3:
                    try:
                        return (int(parts[0]) & 255, int(parts[1]) & 255, int(parts[2]) & 255)
                    except ValueError:
                        return None
        return None

    def animate_neopixel(
        self,
        effect: str,
        *,
        color=None,
        emotions=None,
        segment: str | None = None,
        iterations: int | None = None,
    ):
        url = self.urls.get("neopixel")
        if not url:
            return self.set_interaction_effect(str(effect), force=True, color=color, emotions=emotions)
        payload: dict = {"name": str(effect or "PULSE").strip().upper() or "PULSE"}
        rgb = self._parse_rgb(color)
        if rgb is not None:
            payload["r"], payload["g"], payload["b"] = rgb
        if emotions:
            payload["emotions"] = [str(x) for x in emotions if str(x).strip()]
        if segment:
            payload["segment"] = str(segment)
        if iterations is not None:
            payload["iterations"] = int(iterations)
        return self._post("neopixel", "/animate", payload)

    def set_neopixel(self, effect, emotions=None, color=None, duration=None):
        name = str(effect or "PULSE").strip().upper() or "PULSE"
        duration_ms = 800
        if duration is not None:
            try:
                duration_ms = max(200, int(float(duration) * 1000))
            except (TypeError, ValueError):
                duration_ms = 800
        rgb = self._parse_rgb(color)
        if rgb is not None and self.urls.get("neopixel"):
            return self.animate_neopixel(name, color=rgb, emotions=emotions)
        return self.set_interaction_effect(
            name,
            duration_ms=duration_ms,
            force=True,
            color=color,
            emotions=emotions,
        )

    def emote_neopixel(self, emotions: list[str], duration: float = 0.25):
        """Play palette-based emotion colors via /neopixel/emote."""
        url = self.urls.get("neopixel")
        if not url or not emotions:
            return None
        try:
            import requests

            params: dict = {"duration": float(duration)}
            if len(emotions) == 1:
                params["emotion"] = str(emotions[0])
            else:
                params["emotions"] = [str(e) for e in emotions if str(e).strip()]
            return requests.post(f"{url}/emote", params=params, timeout=self._timeout("default_post_s"))
        except Exception:
            return None

    def set_neopixel_segment_effect(self, segment: str, effect: str, color=None, emotions=None, iterations=None):
        name = str(effect or "PULSE").strip().upper() or "PULSE"
        rgb = self._parse_rgb(color)
        url = self.urls.get("neopixel")
        if url:
            return self.animate_neopixel(
                name,
                color=rgb,
                emotions=emotions,
                segment=str(segment or "").strip() or None,
                iterations=iterations,
            )
        return self.set_neopixel(name, emotions=emotions, color=color)

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

    def speak(self, text, tone=None, engine=None, language=None, trace_id=None):
        payload = self._build_speak_payload(
            text, tone=tone, engine=engine, language=language, trace_id=trace_id,
        )
        return self._post("speak", "/say", payload)

    def _build_speak_payload(self, text, tone=None, engine=None, language=None, trace_id=None):
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
        payload = {"text": text_value}
        if tone:
            payload["tone"] = tone
        if engine:
            payload["engine"] = engine
        if language:
            payload["language"] = str(language)
        if trace_id:
            payload["trace_id"] = str(trace_id)
        return payload

    def speak_stream(self, text, tone=None, engine=None, language=None, max_chunk_chars=None, trace_id=None):
        """Chunked TTS via /speak/say_stream; blocks until the stream job finishes."""
        payload = self._build_speak_payload(
            text, tone=tone, engine=engine, language=language, trace_id=trace_id,
        )
        if not str(payload.get("text", "")).strip():
            return {"ok": False, "error": "text is empty"}
        if max_chunk_chars is not None:
            payload["max_chunk_chars"] = int(max_chunk_chars)
        elif self.speech_stream_cfg.get("stream_max_chunk_chars"):
            payload["max_chunk_chars"] = int(self.speech_stream_cfg.get("stream_max_chunk_chars"))

        start_timeout = float(self.request_timeouts.get("speak_stream_start_s", 4.0))
        resp = self._post("speak", "/say_stream", payload, timeout_s=start_timeout)
        if not resp or not resp.get("ok"):
            return self.speak(text, tone=tone, engine=engine, language=language, trace_id=trace_id)

        job_id = str(resp.get("job_id") or "").strip()
        if not job_id:
            return resp

        poll_s = float(self.speech_stream_cfg.get("stream_poll_interval_s", 0.12))
        max_wait = float(self.speech_stream_cfg.get("stream_max_wait_s", 90.0))
        deadline = time.time() + max_wait
        while time.time() < deadline:
            status = self._get("speak", f"/jobs/{job_id}", timeout_s=2.0)
            if not isinstance(status, dict):
                time.sleep(poll_s)
                continue
            job = status.get("job") if isinstance(status.get("job"), dict) else status
            state = str(job.get("status") or "").strip().lower()
            if state in {"done", "failed", "interrupted"}:
                return {"ok": state != "failed", "status": state, "job": job, "job_id": job_id}
            time.sleep(poll_s)
        return {"ok": False, "error": "stream_timeout", "job_id": job_id}

    def speak_preferred(self, text, tone=None, engine=None, language=None, trace_id=None):
        if bool(self.speech_stream_cfg.get("use_stream_tts", False)):
            return self.speak_stream(
                text, tone=tone, engine=engine, language=language, trace_id=trace_id,
            )
        return self.speak(text, tone=tone, engine=engine, language=language, trace_id=trace_id)

    def chat(self, query, apply_actions: bool | None = None, source_lang: str | None = None, response_lang: str | None = None):
        # apply_actions=None leaves the decision to the ollama service config
        # (actions.default_apply), so tag-based actions work on the fallback path.
        params = {"query": query}
        if apply_actions is not None:
            params["apply_actions"] = str(bool(apply_actions)).lower()
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

    def set_interaction_effect(
        self,
        name: str,
        duration_ms: int = 800,
        force: bool = False,
        color=None,
        emotions=None,
    ):
        payload: dict = {
            "name": str(name),
            "duration_ms": int(duration_ms),
            "force": bool(force),
        }
        rgb = self._parse_rgb(color)
        if rgb is not None:
            payload["r"], payload["g"], payload["b"] = rgb
        elif color is not None:
            payload["color"] = color
        if emotions:
            payload["emotions"] = [str(x) for x in emotions if str(x).strip()]
        return self._post("interactions", "/effect", payload)

    def set_interaction_base(self, name: str, color=None):
        payload = {"name": str(name)}
        if color is not None:
            payload["color"] = color
        return self._post("interactions", "/base", payload)

    def set_expression_event(self, event_type, data=None):
        return self._post("expression", "/event", {"type": str(event_type), "data": data or {}})

    def set_speech_tracking(self, enabled):
        endpoint = "/track/start" if enabled else "/track/stop"
        return self._post("speech", endpoint)

    def set_stt_suppressed(self, suppressed: bool):
        return self._post("speech", "/stt/suppress", {"enabled": bool(suppressed)}, timeout_s=0.25)

    def get_operational_mode(self) -> str:
        data = self._get("state_manager", "/get")
        if isinstance(data, dict):
            return str(data.get("operational", "idle")).strip().lower() or "idle"
        return "idle"

    def stop_speaking(self):
        return self._post("speak", "/stop", timeout_s=0.35)

    def start_speech_listening(self):
        return self._post("speech", "/start", timeout_s=0.35)

    def interrupt_agent_speech(self):
        try:
            from modules.gateway.url import gateway_url, resolve_gateway_base_url

            base = str(self.urls.get("agent_core") or gateway_url(resolve_gateway_base_url(), "/agent")).rstrip("/")
        except Exception:
            base = str(self.urls.get("agent_core") or "http://127.0.0.1:8080/agent").rstrip("/")
        try:
            resp = requests.post(f"{base}/speech/interrupt", timeout=0.35)
            return resp.json() if resp.status_code == 200 else None
        except Exception as exc:
            logger.debug("interrupt_agent_speech failed: %s", exc)
            return None

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

        endpoint = "/status" if svc in ("speak", "speech") else "/healthz"
        try:
            resp = requests.get(f"{url}{endpoint}", timeout=0.6)
            ok = resp.status_code == 200
            if ok and svc == "ollama":
                try:
                    payload = resp.json()
                    ok = bool(payload.get("ok", False))
                except Exception:
                    ok = False
            elif ok and svc == "speak":
                try:
                    payload = resp.json()
                    ok = bool(payload.get("ready", False))
                except Exception:
                    ok = False
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
        url = self._agent_core_url()
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

    def world_memory_context(self, query: str, limit: int = 8):
        return self._get("autonomy", "/memory/context", params={"q": str(query or ""), "limit": int(limit or 8)}, timeout_s=1.0)

    def world_memory_recall(self, query: str, limit: int = 8):
        return self._get("autonomy", "/memory/search", params={"q": str(query or ""), "limit": int(limit or 8)}, timeout_s=1.0)

    def world_memory_observe(self, payload: dict | None = None):
        return self._post("autonomy", "/memory/observe", json=payload or {}, timeout_s=1.0)

    def execute_rest_corner(self, payload: dict | None = None):
        return self._post("autonomy", "/navigation/rest-corner", json=payload or {}, timeout_s=1.5)

    def emit_agent_event(self, event_type: str, payload: dict | None = None):
        if payload is None:
            payload = {}
        url = self._agent_core_url()
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
