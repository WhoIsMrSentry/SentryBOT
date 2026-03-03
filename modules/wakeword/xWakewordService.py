from __future__ import annotations
import argparse
import logging
import os
from pathlib import Path
import threading
import time
from threading import Event, Lock
from typing import Optional

try:
    import requests  # type: ignore
except Exception:
    requests = None  # type: ignore

from fastapi import FastAPI

from modules.wakeword.config_loader import load_config
from modules.wakeword.services.wakeword_detector import WakewordDetector
from modules.wakeword.services.openwakeword_runner import OpenWakewordRunner
from modules.speech.services.audio_capture import AudioCapture
from modules.speech.services.recognizer import Recognizer, RecognitionResult

try:
    from modules.logwrapper import init_logging as _init_global_logging  # type: ignore
    _init_global_logging()
except Exception:
    pass

logger = logging.getLogger("wakeword")


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


def _resolve_model_paths(rec_cfg: dict) -> dict:
    cfg = dict(rec_cfg or {})
    module_root = Path(__file__).resolve().parent
    model_path = cfg.get("model_path")
    if model_path and not os.path.isabs(str(model_path)):
        cfg["model_path"] = str((module_root / str(model_path)).resolve())
    language_models = cfg.get("language_models")
    if isinstance(language_models, dict):
        resolved = {}
        for lang, path in language_models.items():
            if isinstance(path, str) and not os.path.isabs(path):
                resolved[lang] = str((module_root / path).resolve())
            else:
                resolved[lang] = path
        cfg["language_models"] = resolved
    return cfg


class WakewordActions:
    def __init__(self, cfg: dict):
        self.speech_start_url = str(cfg.get("speech_start_url", ""))
        self.speech_stop_url = str(cfg.get("speech_stop_url", ""))
        self.speech_last_url = str(cfg.get("speech_last_url", ""))
        self.interactions_event_url = str(cfg.get("interactions_event_url", ""))
        self.listen_window_sec = float(cfg.get("listen_window_sec", 8.0))
        self.stop_on_final = bool(cfg.get("stop_on_final", True))
        self.poll_interval_ms = int(cfg.get("poll_interval_ms", 200))

    def start_speech(self) -> None:
        _post_json(self.speech_start_url)

    def stop_speech(self) -> None:
        _post_json(self.speech_stop_url)

    def emit_event(self, event_type: str, wakeword: str) -> None:
        if not self.interactions_event_url:
            return
        _post_json(self.interactions_event_url, {"type": event_type, "wakeword": wakeword})

    def has_final_speech(self) -> bool:
        if not self.speech_last_url:
            return False
        data = _get_json(self.speech_last_url)
        return bool(data.get("final") and str(data.get("text", "")).strip())


class WakewordService:
    """Continuously listen for a wakeword and start/stop speech recognition."""

    def __init__(self, config_path: Optional[str] = None):
        self.cfg = load_config(config_path)
        self._stop_event = Event()
        self._listening = False
        self._lock = Lock()
        self._last_trigger_ts = 0.0
        self._active_window = False
        self._thread: Optional[threading.Thread] = None
        self._degraded_reason: Optional[str] = None

        self.capture = AudioCapture(self.cfg.get("audio", {}))
        wake_cfg = self.cfg.get("wakeword", {})
        self.engine = str(wake_cfg.get("engine", "vosk")).lower()
        self.detector = WakewordDetector(wake_cfg)
        self._openwakeword = None
        self._recognizer = None
        if self.engine == "openwakeword":
            try:
                self._openwakeword = OpenWakewordRunner(self.cfg.get("openwakeword", {}))
            except Exception as exc:
                self._degraded_reason = str(exc)
                logger.warning("wakeword openwakeword unavailable, falling back to vosk: %s", exc)
                self.engine = "vosk"
                try:
                    self._recognizer = Recognizer(_resolve_model_paths(self.cfg.get("recognition", {})))
                    self._degraded_reason = None
                except Exception as rec_exc:
                    self._degraded_reason = str(rec_exc)
        else:
            self._recognizer = Recognizer(_resolve_model_paths(self.cfg.get("recognition", {})))
        self.actions = WakewordActions(self.cfg.get("actions", {}))

    def start(self) -> None:
        with self._lock:
            if self._listening:
                return
            self._listening = True
        self._stop_event.clear()
        try:
            if self._openwakeword is None and self._recognizer is None:
                logger.warning("wakeword service running degraded: no engine available")
                self._degraded_reason = self._degraded_reason or "no wakeword engine available"
                return
            stream = self.capture.stream()
            if self.engine == "openwakeword" and self._openwakeword is not None:
                for label in self._openwakeword.run(stream):
                    if self._stop_event.is_set():
                        break
                    self._on_wakeword(label)
            else:
                for result in self._recognizer.run(stream):
                    if self._stop_event.is_set():
                        break
                    self._handle_result(result)
        except Exception as exc:
            self._degraded_reason = str(exc)
            logger.warning("wakeword listener stopped, running degraded: %s", exc)
        finally:
            with self._lock:
                self._listening = False

    def start_background(self) -> None:
        with self._lock:
            if self._listening:
                return
        self._thread = threading.Thread(target=self.start, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self.capture.stop()
        with self._lock:
            self._listening = False
            self._active_window = False

    def _handle_result(self, result: RecognitionResult) -> None:
        if not result.text:
            return
        if result.is_final:
            conf = result.confidence if result.confidence is not None else 0.0
            if conf < self.detector.cfg.min_confidence:
                return
        else:
            if not self.detector.cfg.trigger_on_partial:
                return
        match = self.detector.match(result.text)
        if match:
            self._on_wakeword(match)

    def _on_wakeword(self, wakeword: str) -> None:
        now = _now()
        with self._lock:
            if self._active_window:
                return
            if now - self._last_trigger_ts < self.detector.cfg.cooldown_sec:
                return
            self._last_trigger_ts = now
            self._active_window = True
        threading.Thread(target=self._command_window, args=(wakeword,), daemon=True).start()

    def _command_window(self, wakeword: str) -> None:
        try:
            self.actions.emit_event("wakeword.detected", wakeword)
            self.actions.start_speech()
            if self.actions.listen_window_sec <= 0:
                return
            deadline = _now() + self.actions.listen_window_sec
            while _now() < deadline and not self._stop_event.is_set():
                if self.actions.stop_on_final and self.actions.has_final_speech():
                    break
                time.sleep(max(0.05, self.actions.poll_interval_ms / 1000.0))
            self.actions.stop_speech()
        finally:
            with self._lock:
                self._active_window = False

    @property
    def listening(self) -> bool:
        with self._lock:
            return self._listening

    def status(self) -> dict:
        with self._lock:
            return {
                "listening": self._listening,
                "active_window": self._active_window,
                "last_trigger_ts": self._last_trigger_ts,
                "wakewords": list(self.detector.cfg.words),
                "engine": self.engine,
                "degraded": bool(self._degraded_reason),
                "degraded_reason": self._degraded_reason,
            }


def create_app(config_path: str | None = None) -> FastAPI:
    service = WakewordService(config_path)
    app = FastAPI()
    from modules.wakeword.api import get_router  # local import to avoid circular
    app.include_router(get_router(service))
    return app


def main():
    parser = argparse.ArgumentParser(description="Wakeword detection service")
    parser.add_argument("--config", type=str, default=None, help="Path to config.yml")
    parser.add_argument("--api", action="store_true", help="Run FastAPI server using config server.host/port")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.api:
        import uvicorn  # type: ignore
        cfg = load_config(args.config)
        host = str(cfg.get("server", {}).get("host", "0.0.0.0"))
        port = int(cfg.get("server", {}).get("port", 8084))
        uvicorn.run(create_app(args.config), host=host, port=port)
        return

    service = WakewordService(args.config)
    service.start()


if __name__ == "__main__":
    main()
