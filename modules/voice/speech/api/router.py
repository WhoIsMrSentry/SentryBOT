from __future__ import annotations
from fastapi import APIRouter
import requests
import threading
import logging
import time
from threading import Timer, Lock
from typing import TYPE_CHECKING, Any

from modules.voice.speech.services.wake_phrase import contains_wakeword, strip_wakewords

if TYPE_CHECKING:
    from modules.voice.speech.xSpeechService import SpeechService

logger = logging.getLogger("speech.api")

_GATEWAY_BASE = "http://127.0.0.1:8080"
_INTERACTIONS_ENGINE: Any | None = None


def set_interactions_engine(engine: Any | None) -> None:
    global _INTERACTIONS_ENGINE
    _INTERACTIONS_ENGINE = engine


def _gw(path: str) -> str:
    return f"{_GATEWAY_BASE.rstrip('/')}/{path.lstrip('/')}"


def _barge_in_urls() -> tuple[str, ...]:
    return (
        _gw("/speak/stop"),
        _gw("/agent/speech/interrupt"),
        _gw("/speech/start"),
    )


def _notify_autonomy(text: str = "", language: str = ""):
    # 1. Update OLED face subtitle with recognized STT text
    if text:
        try:
            requests.post(
                _gw("/oled_faces/stt_text"),
                json={"text": text, "duration_s": 5.0},
                timeout=0.2,
            )
        except Exception:
            pass

    # 2. Push final transcript so autonomy reacts immediately
    try:
        requests.post(
            _gw("/autonomy/speech"),
            json={"text": text, "language": language, "final": True},
            timeout=0.5,
        )
        return
    except Exception:
        pass
    try:
        requests.post(_gw("/autonomy/interaction"), timeout=0.1)
    except Exception:
        pass


def _push_interaction_event(event_type: str, data: dict | None = None):
    engine = _INTERACTIONS_ENGINE
    if engine is not None and hasattr(engine, "push_event"):
        try:
            engine.push_event(event_type, data or {})
            return
        except Exception:
            pass
    try:
        requests.post(
            _gw("/interactions/event"),
            json={"type": event_type, "data": data or {}},
            timeout=0.1,
        )
    except Exception:
        pass


def _emit_speech_event(name: str, data: dict | None = None):
    if _INTERACTIONS_ENGINE is not None:
        _push_interaction_event(name, data)
        return
    threading.Thread(target=_push_interaction_event, args=(name, data), daemon=True).start()


def _barge_in_for_wakeword() -> None:
    for url in _barge_in_urls():
        try:
            requests.post(url, json={}, timeout=0.25)
        except Exception:
            pass
    logger.info("Wakeword barge-in: stopped TTS and opened listening")


def get_router(service: SpeechService, gateway_base_url: str = "") -> APIRouter:
    global _GATEWAY_BASE
    if gateway_base_url:
        _GATEWAY_BASE = str(gateway_base_url).rstrip("/")
    router = APIRouter()

    @router.get("/speech/status")
    async def status():
        stt = service.stt_status() if hasattr(service, "stt_status") else {}
        return {
            "ok": bool(stt.get("available", False)),
            "listening": service.listening,
            "model_ready": bool(stt.get("available", False)),
            "stt_available": bool(stt.get("available", False)),
            "stt_suppressed": bool(getattr(service, "is_stt_suppressed", lambda: False)()),
            "stt": stt,
        }

    last: dict | None = {"text": None, "language": getattr(service, "source_language", "tr"), "ts": 0.0}
    last_nonempty_text = ""
    last_partial_text = ""
    last_partial_ts = 0.0
    last_vu_emit_ts = 0.0
    speaking = False
    speaking_lock = Lock()
    vu_stop = threading.Event()
    vu_thread: threading.Thread | None = None
    _final_timer: threading.Timer | None = None
    _pending_text = ""

    def _execute_final():
        nonlocal last, last_nonempty_text, _pending_text
        text = _pending_text
        _pending_text = ""
        if not text:
            return
            
        language = getattr(service, "source_language", "tr")
        if hasattr(service, "finalize_stt"):
            text, language = service.finalize_stt(text)
        if text:
            last_nonempty_text = text
        last = {
            "text": text or None,
            "final": True,
            "confidence": 1.0,
            "language": language,
            "ts": time.time(),
        }
        if text:
            logger.info("STT >>> %s (lang=%s)", text, language)
        else:
            logger.debug("stt final empty")
        
        last_partial_text = ""
        
        if text:
            final_spoken = text
            _emit_speech_event("speech.final", {"text": final_spoken, "language": language})
            threading.Thread(
                target=_notify_autonomy,
                args=(final_spoken, language),
                daemon=True,
            ).start()
            if _mark_speaking(True):
                _emit_speech_event("speech.start")
            _schedule_speech_end()

    def _cb(r):
        nonlocal last, last_partial_text, last_partial_ts, last_nonempty_text, last_vu_emit_ts, _final_timer, _pending_text
        now = time.time()
        if hasattr(service, "is_stt_suppressed") and service.is_stt_suppressed():
            return
        text = (r.text or "").strip()
        language = getattr(service, "source_language", "tr")

        if r.is_final:
            if not text and not _pending_text:
                return
            _pending_text = text or _pending_text
            if _final_timer:
                _final_timer.cancel()
            _final_timer = threading.Timer(1.5, _execute_final)
            _final_timer.daemon = True
            _final_timer.start()
        else:
            if _final_timer:
                _final_timer.cancel()
                _final_timer = None

            if text and contains_wakeword(text):
                remainder = strip_wakewords(text)
                if len(remainder.split()) < 2:
                    threading.Thread(target=_barge_in_for_wakeword, daemon=True).start()

            # Throttle partial logs to avoid log spam but keep visibility.
            if text and (text != last_partial_text or (now - last_partial_ts) >= 0.35):
                logger.info("STT (partial) >>> %s", text)
                last_partial_text = text
                last_partial_ts = now
                try:
                    requests.post(
                        _gw("/oled_faces/stt_text"),
                        json={"text": text, "duration_s": 3.0},
                        timeout=0.1,
                    )
                except Exception:
                    pass

    @router.post("/speech/start")
    async def start():
        was_listening = service.listening
        logger.info("speech start requested (was_listening=%s)", was_listening)
        stt = service.stt_status() if hasattr(service, "stt_status") else {}
        if not stt.get("available", False):
            logger.warning(
                "speech start rejected: stt unavailable primary_language=%s reason=%s",
                stt.get("primary_language"),
                stt.get("reason"),
            )
            return {"ok": False, "listening": False, "reason": "stt_unavailable", "stt": stt}
        if hasattr(service, "clear_utterance_buffer"):
            service.clear_utterance_buffer()
        service.start_background(on_result=_cb)
        _start_vu_monitor()
        logger.info("speech start handled (listening=%s)", service.listening)
        if not was_listening:
            _emit_speech_event("speech.listen.start")
        return {"ok": True, "listening": service.listening, "stt": stt}

    @router.post("/speech/stop")
    async def stop():
        _stop_vu_monitor()
        service.stop()
        _emit_speech_event("speech.listen.end")
        if _mark_speaking(False):
            _emit_speech_event("speech.end")
        return {"ok": True, "listening": service.listening}

    @router.get("/speech/last")
    async def last_result():
        return last or {}

    @router.get("/speech/direction")
    async def direction():
        angle = service.last_angle if hasattr(service, "last_angle") else None
        if angle is None:
            return {"ok": False, "angle": None}
        return {"ok": True, "angle": angle}

    @router.post("/speech/track/start")
    async def track_start():
        try:
            service.track_start()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @router.post("/speech/track/stop")
    async def track_stop():
        try:
            service.track_stop()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @router.get("/speech/track/status")
    async def track_status():
        return service.track_status()

    @router.post("/speech/stt/suppress")
    async def stt_suppress(body: dict | None = None):
        enabled = bool((body or {}).get("enabled", True))
        if hasattr(service, "set_stt_suppressed"):
            service.set_stt_suppressed(enabled)
        return {"ok": True, "suppressed": enabled}

    return router
