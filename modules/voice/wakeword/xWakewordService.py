from __future__ import annotations

import argparse
import logging
import math
import threading
import time
from threading import Event, Lock, Thread
from typing import Any, Iterable, Iterator, Optional

from fastapi import FastAPI

from modules.voice.audio_router import get_audio_router
from modules.voice.wakeword.config_loader import load_audio_router_config, load_config
from modules.voice.wakeword.services.openwakeword_runner import OpenWakewordRunner
from modules.voice.wakeword.services.wakeword_actions import WakewordActions, _now
from modules.voice.wakeword.services.wakeword_detector import WakewordDetector

try:
    from modules.common.logger import init_logging as _init_global_logging  # type: ignore

    _init_global_logging()
except Exception:
    pass

logger = logging.getLogger("wakeword")


def _chunk_rms_int16(chunk: bytes) -> float:
    """Fast int16 PCM RMS computation without allocating full float streams."""
    if not chunk or len(chunk) < 2:
        return 0.0
    try:
        import numpy as np  # type: ignore

        usable = (len(chunk) // 2) * 2
        if usable <= 0:
            return 0.0
        arr = np.frombuffer(chunk[:usable], dtype=np.int16)
        if arr.size == 0:
            return 0.0
        return float(math.sqrt(float(np.mean(arr.astype(np.float32) ** 2))))
    except Exception:
        return 0.0


class WakewordService:
    """Continuously listen for a wakeword and start/stop speech recognition."""

    def __init__(self, config_path: Optional[str] = None):
        self.cfg = load_config(config_path)
        self._stop_event = Event()
        self._listening = False
        self._lock = Lock()
        self._last_trigger_ts = 0.0
        self._active_window = False
        self._thread: Optional[Thread] = None
        self._stream_iter: Optional[Iterator[bytes]] = None
        self._degraded_reason: Optional[str] = None
        self._restart_attempts = 0

        # Initialize audio router
        audio_router_cfg = load_audio_router_config()
        self._audio_router = get_audio_router(audio_router_cfg)
        self._audio_router.start()

        wake_cfg = self.cfg.get("wakeword", {})
        self.engine = "openwakeword"
        self.detector = WakewordDetector(wake_cfg)
        self._openwakeword: Optional[OpenWakewordRunner] = None
        ow_cfg = dict(self.cfg.get("openwakeword", {}) or {})
        self._vad_gate_enabled = bool(ow_cfg.get("vad_gate_enabled", True))
        self._vad_min_rms = float(ow_cfg.get("vad_min_rms", 35.0))
        self._vad_hangover_sec = max(0.0, float(ow_cfg.get("vad_hangover_sec", 0.6)))
        self._vad_hangover_until = 0.0
        self._energy_gate_skipped = 0
        self._energy_gate_passed = 0

        try:
            audio_channels = int((self.cfg.get("audio", {}) or {}).get("channels", 1))
            ow_cfg.setdefault("input_channels", audio_channels)
            self._openwakeword = OpenWakewordRunner(ow_cfg)
        except Exception as exc:
            self._degraded_reason = str(exc)
            logger.warning("wakeword openwakeword unavailable: %s", exc)

        self.actions = WakewordActions(self.cfg.get("actions", {}))
        rec_vad = (self.cfg.get("recognition", {}) or {}).get("vad", {})
        if isinstance(rec_vad, dict) and rec_vad.get("enabled"):
            self.actions.vad_enabled = True
        logger.info(
            "wakeword engine=%s detector_words=%s degraded=%s",
            self.engine,
            list(self.detector.cfg.words),
            bool(self._degraded_reason),
        )

    def _should_feed_wakeword(self, chunk: bytes, capture: Any = None) -> bool:
        """Lightweight RMS/VAD gate avoiding ONNX inference on silent frames."""
        if not chunk:
            return False
        if not self._vad_gate_enabled or self._vad_min_rms <= 0.0:
            self._energy_gate_passed += 1
            return True
        if self._openwakeword is not None and not getattr(self._openwakeword, "_calibration_done", True):
            self._energy_gate_passed += 1
            return True

        now = time.monotonic()
        vad = getattr(capture, "_vad", None) if capture is not None else None
        if vad is not None and getattr(vad, "is_speaking", False):
            self._vad_hangover_until = now + self._vad_hangover_sec
            self._energy_gate_passed += 1
            return True

        if _chunk_rms_int16(chunk) >= self._vad_min_rms:
            self._vad_hangover_until = now + self._vad_hangover_sec
            self._energy_gate_passed += 1
            return True

        if now < self._vad_hangover_until:
            self._energy_gate_passed += 1
            return True

        self._energy_gate_skipped += 1
        return False

    def _gated_stream(self, stream: Iterable[bytes], capture: Any = None) -> Iterator[bytes]:
        for chunk in stream:
            if self._stop_event.is_set():
                break
            if self._should_feed_wakeword(chunk, capture):
                yield chunk

    def start(self) -> None:
        with self._lock:
            if self._listening:
                return
            self._listening = True
        self._stop_event.clear()
        retry_delay: Optional[float] = None
        try:
            if self._openwakeword is None:
                logger.warning("wakeword service running degraded: openwakeword not available")
                self._degraded_reason = self._degraded_reason or "openwakeword not available"
                return

            capture = self._audio_router.get_capture()
            if capture is None:
                raise RuntimeError("audio router capture not running")

            logger.info("wakeword listening started (engine=openwakeword)")
            self._stream_iter = iter(capture.stream(stop_event=self._stop_event))
            self._restart_attempts = 0

            for label in self._openwakeword.run(self._gated_stream(self._stream_iter, capture)):
                if self._stop_event.is_set():
                    break
                self._on_wakeword(label)

        except Exception as exc:
            self._degraded_reason = str(exc)
            attempts = self._restart_attempts + 1
            self._restart_attempts = attempts
            logger.warning("wakeword listener stopped, running degraded: %s", exc)
            if not self._stop_event.is_set():
                if attempts <= 5:
                    retry_delay = min(30.0, 0.5 * (2 ** (attempts - 1)))
                else:
                    logger.error(
                        "wakeword listener failed %d times consecutively; staying degraded",
                        attempts,
                    )
        finally:
            it = self._stream_iter
            self._stream_iter = None
            if hasattr(it, "close"):
                try:
                    it.close()  # type: ignore[misc]
                except Exception:
                    pass
            with self._lock:
                self._listening = False

        if retry_delay is not None and not self._stop_event.is_set():
            if not self._stop_event.wait(retry_delay):
                self.start_background()

    def start_background(self) -> None:
        with self._lock:
            if self._listening:
                return
            t = Thread(target=self.start, daemon=True)
            self._thread = t
        t.start()

    def _ensure_listener_restarted(self, retries: int = 6, delay_sec: float = 0.2) -> None:
        for _ in range(max(1, retries)):
            self.start_background()
            time.sleep(max(0.05, delay_sec))
            if self.listening:
                return

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            it = self._stream_iter
            self._stream_iter = None
            self._listening = False
            self._active_window = False
            thr = self._thread
            self._thread = None
        if hasattr(it, "close"):
            try:
                it.close()  # type: ignore[misc]
            except Exception:
                pass
        if thr is not None and thr is not threading.current_thread() and thr.is_alive():
            thr.join(timeout=1.5)

    def _on_wakeword(self, wakeword: str) -> None:
        now = _now()
        with self._lock:
            if self._active_window:
                return
            if now - self._last_trigger_ts < self.detector.cfg.cooldown_sec:
                return
            self._last_trigger_ts = now
            self._active_window = True
        logger.info("openwakeword detected: %s", wakeword)
        self.actions.interrupt_robot_speech()
        logger.info("wakeword candidate: %s at %f (barge-in)", wakeword, now)
        Thread(target=self._command_window, args=(wakeword,), daemon=True).start()

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
                if self._stop_event.is_set():
                    break
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

    def status(self) -> dict[str, Any]:
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
                "energy_gate": {
                    "enabled": self._vad_gate_enabled,
                    "min_rms": self._vad_min_rms,
                    "passed_chunks": self._energy_gate_passed,
                    "skipped_chunks": self._energy_gate_skipped,
                },
            }


def create_app(config_path: str | None = None) -> FastAPI:
    service = WakewordService(config_path)
    app = FastAPI()
    from modules.voice.wakeword.api import get_router

    app.include_router(get_router(service))
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Wakeword detection service")
    parser.add_argument("--config", type=str, default=None, help="Path to config.yml")
    parser.add_argument("--api", action="store_true", help="Run FastAPI server using config server.host/port")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.api:
        import uvicorn  # type: ignore

        cfg = load_config(args.config)
        host = str(cfg.get("server", {}).get("host", "127.0.0.1"))
        port = int(cfg.get("server", {}).get("port", 8084))
        uvicorn.run(create_app(args.config), host=host, port=port, log_config=None)
        return

    service = WakewordService(args.config)
    service.start()


if __name__ == "__main__":
    main()
