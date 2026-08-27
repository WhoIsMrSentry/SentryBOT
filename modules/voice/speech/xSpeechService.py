from __future__ import annotations

import argparse
import copy
import logging
from threading import Event, Lock
import time
from typing import Optional, Callable, Iterable, TYPE_CHECKING
from fastapi import FastAPI

from modules.voice.speech.config_loader import load_config, load_audio_router_config
from modules.voice.speech.services.recognizer import Recognizer, RecognitionResult
from modules.voice.speech.services.stt_language import resolve_stt_text_and_language
from modules.voice.speech.services.direction import DirectionEstimator
from modules.voice.speech.services.pan_tilt import PanTiltController
from modules.voice.audio_router import (
    get_audio_router, AudioRouterConfig, AudioConfig
)
from .services.audio_filters import SpeechAudioFilterMixin
from .services.sound_tracking import SpeechSoundTrackingMixin

if TYPE_CHECKING:
    from modules.voice.speech.api import get_router  # type: ignore

try:
    from modules.runtime_console.logwrapper import init_logging as _init_global_logging  # type: ignore
    _init_global_logging()
except Exception:
    pass

logger = logging.getLogger("speech")


class SpeechService(SpeechAudioFilterMixin, SpeechSoundTrackingMixin):
    """High-level facade to run audio capture and speech recognition."""

    def __init__(self, config_path: Optional[str] = None):
        self.cfg = load_config(config_path)
        self._stop_event = Event()
        self._listening = False
        self._listen_lock = Lock()
        self._result_lock = Lock()
        self._on_result_cb: Optional[Callable[[RecognitionResult], None]] = None
        self._thread = None
        
        # Initialize audio router
        audio_router_cfg = load_audio_router_config()
        self._audio_router = get_audio_router(audio_router_cfg)
        self._audio_router.start()
        
        rec_cfg = self.cfg.get("recognition", {}) or {}
        self.recognizer = Recognizer(rec_cfg)
        self.source_language = str(rec_cfg.get("source_language") or rec_cfg.get("language") or "tr")
        self._default_language = str(rec_cfg.get("default_language") or self.source_language or "tr")
        self._auto_language = bool(rec_cfg.get("auto_language", True))
        self._auto_switch_model = bool(rec_cfg.get("auto_switch_model", True))
        self._dual_decode_margin = float(rec_cfg.get("dual_decode_margin", 0.6))
        self._prefer_online_detect = bool(rec_cfg.get("prefer_online_detect", True))
        self._dual_decode_only_if_ambiguous = bool(rec_cfg.get("dual_decode_only_if_ambiguous", True))
        self._utterance_pcm = bytearray()
        self._max_utterance_bytes = int(
            rec_cfg.get("utterance_buffer_sec", 20) or 20
        ) * int(rec_cfg.get("samplerate", 16000) or 16000) * 2
        self._secondary_recognizer: Optional[Recognizer] = None
        self._extra_recognizers: dict[str, Recognizer] = {}
        self._last_audio_level = 0.0
        self._stt_input_gain = float(rec_cfg.get("input_gain", 1.0))

        # Audio router will provide the stream
        # Direction estimator - will be initialized when stream starts
        self.direction_enabled = False
        self._direction = None
        self._last_angle = None

        pt_cfg = self.cfg.get("pan_tilt", {})
        self._pan = PanTiltController(pt_cfg, sender=self._send_pan)
        self._tracking = False
        self._stt_suppressed = False
        self._stt_suppress_lock = Lock()
        self._stt_suppressed_until = 0.0
        self._head_arbiter = None
        
        self._stream_iter = None

    def set_stt_suppressed(self, suppressed: bool, ttl_s: float = 15.0) -> None:
        with self._stt_suppress_lock:
            self._stt_suppressed = bool(suppressed)
            if suppressed:
                self._stt_suppressed_until = time.time() + float(ttl_s)
            else:
                self._stt_suppressed_until = 0.0

    def is_stt_suppressed(self) -> bool:
        with self._stt_suppress_lock:
            if not self._stt_suppressed:
                return False
            if self._stt_suppressed_until > 0.0 and time.time() >= self._stt_suppressed_until:
                self._stt_suppressed = False
                self._stt_suppressed_until = 0.0
                return False
            return True

    def stt_status(self) -> dict:
        primary = self.recognizer.status() if self.recognizer is not None else {"ok": False, "error": "recognizer missing"}
        languages: dict[str, dict] = {}
        rec_cfg = self.cfg.get("recognition", {}) if isinstance(self.cfg.get("recognition", {}), dict) else {}
        language_models = rec_cfg.get("language_models") if isinstance(rec_cfg.get("language_models"), dict) else {}
        primary_lang = str(primary.get("language") or rec_cfg.get("language") or self.source_language or "tr").split("-", 1)[0].lower()
        languages[primary_lang] = primary
        for lang, recognizer in self._extra_recognizers.items():
            try:
                languages[str(lang).split("-", 1)[0].lower()] = recognizer.status()
            except Exception as exc:
                languages[str(lang).split("-", 1)[0].lower()] = {"ok": False, "error": str(exc)}
        for lang in language_models.keys():
            key = str(lang).split("-", 1)[0].lower()
            if key in languages:
                continue
            cfg = copy.deepcopy(rec_cfg)
            cfg["language"] = lang
            cfg.pop("model_path", None)
            try:
                languages[key] = Recognizer(cfg).status()
            except Exception as exc:
                languages[key] = {"ok": False, "language": key, "error": str(exc)}
        ready_languages = [primary_lang] if primary.get("ok") else []
        missing_languages = [] if primary.get("ok") else [primary_lang]
        available = bool(primary.get("ok"))
        return {
            "available": available,
            "model_ready": available,
            "listening": self.listening,
            "suppressed": self.is_stt_suppressed(),
            "primary_language": primary_lang,
            "default_language": self._default_language,
            "auto_language": bool(self._auto_language),
            "auto_switch_model": bool(self._auto_switch_model),
            "primary": primary,
            "languages": {primary_lang: primary},
            "ready_languages": ready_languages,
            "missing_languages": missing_languages,
            "reason": "ready" if available else (primary.get("error") or "speech_recognition backend unavailable"),
        }

    def is_stt_available(self) -> bool:
        return bool(self.stt_status().get("available"))

    def start(self, on_result: Optional[Callable[[RecognitionResult], None]] = None) -> None:
        with self._listen_lock:
            if self._listening:
                return
            self._listening = True
        if on_result is not None:
            with self._result_lock:
                self._on_result_cb = on_result
        self._stop_event.clear()
        try:
            stt_status = self.stt_status()
            if not stt_status.get("available"):
                logger.warning(
                    "speech stt unavailable: primary_language=%s reason=%s",
                    stt_status.get("primary_language"),
                    stt_status.get("reason"),
                )
                return
            
            capture = self._audio_router.get_capture()
            if capture is None:
                raise RuntimeError("audio router capture not running")
            self._stream_iter = iter(capture.stream())

            for result in self.recognizer.run(self._direction_wrapper(self._stream_iter)):
                if self.is_stt_suppressed():
                    continue
                if result and result.text:
                    self.last_result = {
                        "text": result.text,
                        "final": result.is_final,
                        "confidence": result.confidence,
                        "ts": time.time(),
                    }
                cb = None
                with self._result_lock:
                    cb = self._on_result_cb
                if cb:
                    cb(result)
                if self._stop_event.is_set():
                    break
        except Exception as exc:
            logger.warning("speech degraded: recognizer stopped (%s)", exc)
        finally:
            with self._listen_lock:
                self._listening = False

    def finalize_stt(self, text: str) -> tuple[str, str]:
        pcm = bytes(self._utterance_pcm)
        self.clear_utterance_buffer()

        if len(pcm) >= 1600:
            try:
                from modules.voice.speech.services.online_stt import transcribe_google_multilang
                candidate_langs = ["tr", "en"]
                rec_cfg = self.cfg.get("recognition", {}) or {}
                configured_langs = rec_cfg.get("dual_decode_languages")
                if isinstance(configured_langs, list) and configured_langs:
                    candidate_langs = [str(l).split("-")[0].lower() for l in configured_langs if l]

                cloud_text, detected_lang = transcribe_google_multilang(
                    pcm,
                    samplerate=16000,
                    languages=candidate_langs,
                    default_lang=self._default_language,
                )
                if cloud_text:
                    self.source_language = detected_lang
                    return cloud_text, detected_lang
            except Exception as exc:
                logger.debug("Online Google STT transcription error: %s", exc)

        return str(text or "").strip(), self.source_language or self._default_language

    def start_background(self, on_result: Optional[Callable[[RecognitionResult], None]] = None) -> None:
        import threading

        if on_result is not None:
            with self._result_lock:
                self._on_result_cb = on_result
        with self._listen_lock:
            if self._listening and self._thread is not None and self._thread.is_alive():
                return
        t = threading.Thread(target=self.start, kwargs={"on_result": None}, daemon=True)
        with self._listen_lock:
            self._thread = t
        t.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._stream_iter = None
        with self._listen_lock:
            self._listening = False

    def listen_once(self, timeout_sec: float = 5.0) -> Optional[RecognitionResult]:
        res: Optional[RecognitionResult] = None
        def _cb(r: RecognitionResult):
            nonlocal res
            if r.is_final and not res:
                res = r
                self.stop()
        self.start_background(on_result=_cb)
        self._stop_event.wait(timeout=timeout_sec)
        return res

    @property
    def last_angle(self) -> float | None:
        return self._last_angle

    @property
    def listening(self) -> bool:
        with self._listen_lock:
            return self._listening


def create_app(config_path: str | None = None) -> FastAPI:
    service = SpeechService(config_path)
    app = FastAPI()
    from modules.voice.speech.api import get_router
    app.include_router(get_router(service))
    return app


def main():
    parser = argparse.ArgumentParser(description="Speech input service")
    parser.add_argument("--config", type=str, default=None, help="Path to config.yml")
    parser.add_argument("--listen-once", action="store_true", help="Listen once and print the result")
    parser.add_argument("--api", action="store_true", help="Run FastAPI server using config server.host/port")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.api:
        import uvicorn  # type: ignore
        cfg = load_config(args.config)
        host = str(cfg.get("server", {}).get("host", "0.0.0.0"))
        port = int(cfg.get("server", {}).get("port", 8082))
        uvicorn.run(create_app(args.config), host=host, port=port, log_config=None)
        return

    service = SpeechService(args.config)
    if args.listen_once:
        result = service.listen_once()
        print(result)
    else:
        def printer(r: RecognitionResult):
            logger.info("%s", r)
        service.start(on_result=printer)


if __name__ == "__main__":
    main()
