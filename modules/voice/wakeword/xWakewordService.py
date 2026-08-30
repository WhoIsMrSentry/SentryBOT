from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import threading
import time
from threading import Event, Lock
from typing import Any, Optional

try:
    import audioop
except Exception:
    audioop = None

from fastapi import FastAPI

from modules.voice.wakeword.config_loader import load_config, load_audio_router_config
from modules.voice.wakeword.services.wakeword_detector import WakewordDetector
from modules.voice.wakeword.services.openwakeword_runner import OpenWakewordRunner
from modules.voice.wakeword.services.wakeword_actions import (
    WakewordActions,
    _now,
    _post_json,
    _get_json,
    _normalize_command_text,
    _is_wakeword_only,
)
from modules.voice.audio_router import (
    get_audio_router, AudioRouterConfig, AudioConfig,
    OpenWakeWordConsumerAdapter
)

try:
    from modules.runtime_console.logwrapper import init_logging as _init_global_logging  # type: ignore
    _init_global_logging()
except Exception:
    pass

logger = logging.getLogger("wakeword")


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

        # Initialize audio router
        audio_router_cfg = load_audio_router_config()
        self._audio_router = get_audio_router(audio_router_cfg)
        self._audio_router.start()
        
        self._openwakeword_adapter = None
        
        wake_cfg = self.cfg.get("wakeword", {})
        self.engine = "openwakeword"
        self.detector = WakewordDetector(wake_cfg)
        self._openwakeword = None
        try:
            ow_cfg = dict(self.cfg.get("openwakeword", {}) or {})
            audio_channels = int((self.cfg.get("audio", {}) or {}).get("channels", 1))
            ow_cfg.setdefault("input_channels", audio_channels)
            self._openwakeword = OpenWakewordRunner(ow_cfg)
            # Create adapter and register
            self._openwakeword_adapter = OpenWakeWordConsumerAdapter(self._openwakeword)
        except Exception as exc:
            self._degraded_reason = str(exc)
            logger.warning("wakeword openwakeword unavailable: %s", exc)

        self.actions = WakewordActions(self.cfg.get("actions", {}))
        rec_vad = (self.cfg.get("recognition", {}) or {}).get("vad", {})
        if isinstance(rec_vad, dict) and rec_vad.get("enabled"):
            self.actions.vad_enabled = True
        logger.info("wakeword engine=%s detector_words=%s degraded=%s", self.engine, list(self.detector.cfg.words), bool(self._degraded_reason))

    def start(self) -> None:
        with self._lock:
            if self._listening:
                return
            self._listening = True
        self._stop_event.clear()
        try:
            if self._openwakeword is None:
                logger.warning("wakeword service running degraded: openwakeword not available")
                self._degraded_reason = self._degraded_reason or "openwakeword not available"
                return

            capture = self._audio_router.get_capture()
            if capture is None:
                raise RuntimeError("audio router capture not running")

            logger.info("wakeword listening started (engine=openwakeword)")

            self._stream_iter = iter(capture.stream())
            self._restart_attempts = 0

            for label in self._openwakeword.run(self._stream_iter):
                if self._stop_event.is_set():
                    break
                logger.info("openwakeword detected: %s", label)
                self._on_wakeword(label)

        except Exception as exc:
            self._degraded_reason = str(exc)
            attempts = getattr(self, "_restart_attempts", 0) + 1
            self._restart_attempts = attempts
            logger.warning("wakeword listener stopped, running degraded: %s", exc)
            if not self._stop_event.is_set():
                if attempts <= 5:
                    delay = min(30.0, 0.5 * (2 ** (attempts - 1)))
                    time.sleep(delay)
                    self.start_background()
                else:
                    logger.error(
                        "wakeword listener failed %d times consecutively; staying degraded",
                        attempts,
                    )
        finally:
            with self._lock:
                self._listening = False

    def start_background(self) -> None:
        with self._lock:
            if self._listening:
                return
        self._thread = threading.Thread(target=self.start, daemon=True)
        self._thread.start()

    def _ensure_listener_restarted(self, retries: int = 6, delay_sec: float = 0.2) -> None:
        for _ in range(max(1, retries)):
            self.start_background()
            time.sleep(max(0.05, delay_sec))
            if self.listening:
                return

    def stop(self) -> None:
        self._stop_event.set()
        capture = self._audio_router.get_capture()
        if self._openwakeword_adapter:
            if capture is not None:
                capture.unregister_consumer("wakeword_openwakeword")
            self._openwakeword_adapter.on_stop()
        self._stream_iter = None
        with self._lock:
            self._listening = False
            self._active_window = False

    def _on_wakeword(self, wakeword: str) -> None:
        now = _now()
        with self._lock:
            if self._active_window:
                return
            if now - self._last_trigger_ts < self.detector.cfg.cooldown_sec:
                return
            self._last_trigger_ts = now
            self._active_window = True
        self.actions.interrupt_robot_speech()
        logger.info("wakeword candidate: %s at %f (barge-in)", wakeword, now)
        threading.Thread(target=self._command_window, args=(wakeword,), daemon=True).start()

    def _command_window(self, wakeword: str) -> None:
        try:
            self.actions.emit_event("wakeword.detected", wakeword)
            window_started_ts = _now()
            self.actions.start_speech()
            if self.actions.listen_window_sec <= 0:
                return
            deadline = _now() + self.actions.listen_window_sec
            min_listen = (
                self.actions.min_listen_before_final_sec_vad
                if self.actions.vad_enabled
                else self.actions.min_listen_before_final_sec
            )
            grace_until = window_started_ts + max(0.0, min_listen)

            while _now() < deadline:
                if (
                    _now() >= grace_until
                    and self.actions.stop_on_final
                    and self.actions.has_final_speech(window_started_ts, wakeword)
                ):
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
        openwakeword_ready = bool(self._openwakeword is not None)
        with self._lock:
            return {
                "ok": bool(openwakeword_ready and not self._degraded_reason),
                "listening": self._listening,
                "active_window": self._active_window,
                "last_trigger_ts": self._last_trigger_ts,
                "wakewords": list(self.detector.cfg.words),
                "engine": "openwakeword",
                "engine_ready": openwakeword_ready,
                "degraded": bool(self._degraded_reason),
                "degraded_reason": self._degraded_reason,
                "openwakeword_ready": openwakeword_ready,
            }


def create_app(config_path: str | None = None) -> FastAPI:
    service = WakewordService(config_path)
    app = FastAPI()
    from modules.voice.wakeword.api import get_router
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
        uvicorn.run(create_app(args.config), host=host, port=port, log_config=None)
        return

    service = WakewordService(args.config)
    service.start()


if __name__ == "__main__":
    main()


# sentrybot_batch06e_xwakeword_no_hardware_init_stub
def _sentrybot_batch06e_wakeword_hw_disabled():
    import os as _os
    return (
        str(_os.getenv("SENTRYBOT_NO_HARDWARE", "")).lower() in {"1", "true", "yes", "on"}
        or str(_os.getenv("SENTRYBOT_SKIP_WAKEWORD_AUTOSTART", "")).lower() in {"1", "true", "yes", "on"}
    )

try:
    _sentrybot_batch06e_prev_wakeword_init = xWakewordService.__init__

    def _sentrybot_batch06e_wakeword_init(self, *args, **kwargs):
        if _sentrybot_batch06e_wakeword_hw_disabled():
            self.enabled = False
            self.available = False
            self.running = False
            self.runner = None
            self.thread = None
            self._thread = None
            self.last_detection = None
            self.config = kwargs.get("config") or kwargs.get("config_overrides") or {}
            return None

        return _sentrybot_batch06e_prev_wakeword_init(self, *args, **kwargs)

    xWakewordService.__init__ = _sentrybot_batch06e_wakeword_init

except NameError:
    pass

