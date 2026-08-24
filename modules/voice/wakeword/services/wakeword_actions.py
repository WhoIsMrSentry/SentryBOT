from __future__ import annotations

import logging
import time
from typing import Any

try:
    import requests
except Exception:
    requests = None

from modules.voice.speech.services.wake_phrase import strip_wakewords

logger = logging.getLogger("wakeword.actions")


def _now() -> float:
    return time.time()


def _post_json(url: str, payload: dict | None = None, timeout: float = 0.2) -> None:
    if not url or requests is None:
        return
    try:
        requests.post(url, json=payload or {}, timeout=timeout)
    except Exception as exc:
        logger.debug("wakeword http post failed: %s", exc)


def _get_json(url: str, timeout: float = 0.2) -> dict:
    if not url or requests is None:
        return {}
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            return resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    except Exception:
        return {}
    return {}


def _normalize_command_text(text: str, wakeword: str = "") -> str:
    lowered = strip_wakewords(str(text or ""))
    extra = str(wakeword or "").strip().lower()
    if extra:
        lowered = lowered.replace(extra, " ").strip()
    return " ".join(lowered.split())


def _is_wakeword_only(text: str, wakeword: str = "") -> bool:
    return len(_normalize_command_text(text, wakeword)) < 2


class WakewordActions:
    def __init__(self, cfg: dict):
        self.speech_start_url = str(cfg.get("speech_start_url", ""))
        self.speech_stop_url = str(cfg.get("speech_stop_url", ""))
        self.speech_last_url = str(cfg.get("speech_last_url", ""))
        self.interactions_event_url = str(cfg.get("interactions_event_url", ""))
        self.neopixel_url = str(cfg.get("neopixel_url", ""))
        self.listen_window_sec = float(cfg.get("listen_window_sec", 8.0))
        self.min_listen_before_final_sec = float(cfg.get("min_listen_before_final_sec", 1.5))
        self.min_listen_before_final_sec_vad = float(
            cfg.get("min_listen_before_final_sec_vad", self.min_listen_before_final_sec)
        )
        self.vad_enabled = bool(cfg.get("vad_enabled", False))
        self.stop_on_final = bool(cfg.get("stop_on_final", True))
        self.poll_interval_ms = int(cfg.get("poll_interval_ms", 200))
        self.speak_stop_url = str(cfg.get("speak_stop_url", "http://localhost:8080/speak/stop"))
        self.agent_interrupt_url = str(
            cfg.get("agent_interrupt_url", "http://localhost:8080/agent/speech/interrupt")
        )
        self._interactions_engine: Any | None = None
        self._speech_service: Any | None = None
        self._speak_service: Any | None = None
        self._agent_service: Any | None = None

    def interrupt_robot_speech(self) -> None:
        if self._speak_service is not None and hasattr(self._speak_service, "stop"):
            try:
                self._speak_service.stop()
            except Exception as exc:
                logger.debug("direct speak_service stop failed: %s", exc)
        else:
            _post_json(self.speak_stop_url)

        if self._agent_service is not None and hasattr(self._agent_service, "interrupt"):
            try:
                self._agent_service.interrupt()
            except Exception as exc:
                logger.debug("direct agent_service interrupt failed: %s", exc)
        else:
            _post_json(self.agent_interrupt_url)

    def start_speech(self) -> None:
        if self._speech_service is not None and hasattr(self._speech_service, "start_background"):
            try:
                self._speech_service.start_background()
                return
            except Exception as exc:
                logger.debug("direct speech_service start failed: %s", exc)
        _post_json(self.speech_start_url)

    def stop_speech(self) -> None:
        if self._speech_service is not None and hasattr(self._speech_service, "stop"):
            try:
                self._speech_service.stop()
                return
            except Exception as exc:
                logger.debug("direct speech_service stop failed: %s", exc)
        _post_json(self.speech_stop_url)

    def emit_event(self, event_type: str, wakeword: str) -> None:
        engine = self._interactions_engine
        if engine is not None and hasattr(engine, "push_event"):
            try:
                engine.push_event(event_type, {"wakeword": wakeword})
                return
            except Exception:
                pass
        if not self.interactions_event_url:
            return
        _post_json(self.interactions_event_url, {"type": event_type, "wakeword": wakeword})

    def has_final_speech(self, since_ts: float | None = None, wakeword: str = "") -> bool:
        if self._speech_service is not None:
            res = getattr(self._speech_service, "last_result", None)
            if res is not None:
                text = str(getattr(res, "text", "") or "").strip()
                is_final = bool(getattr(res, "final", False))
                ts = float(getattr(res, "ts", 0.0) or 0.0)
                if not is_final or not text:
                    return False
                if since_ts is not None and ts < float(since_ts):
                    return False
                if _is_wakeword_only(text, wakeword):
                    return False
                return True

        if not self.speech_last_url:
            return False
        data = _get_json(self.speech_last_url)
        if not data.get("final"):
            return False
        text = str(data.get("text", "")).strip()
        if not text:
            return False
        if since_ts is not None:
            try:
                if float(data.get("ts", 0.0)) < float(since_ts):
                    return False
            except Exception:
                return False
        if _is_wakeword_only(text, wakeword):
            return False
        return True

    def _neopixel_post(self, endpoint: str, payload: dict | None = None) -> None:
        if not self.neopixel_url or requests is None:
            return
        try:
            url = f"{self.neopixel_url.rstrip('/')}/{endpoint.lstrip('/')}"
            requests.post(url, json=payload or {}, timeout=0.2)
        except Exception as exc:
            logger.debug("neopixel http post failed: %s", exc)
