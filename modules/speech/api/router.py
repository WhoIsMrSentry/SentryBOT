from __future__ import annotations
from fastapi import APIRouter
import requests
import threading
import logging
import time
from threading import Timer, Lock
from typing import TYPE_CHECKING

from modules.speech.services.wake_phrase import contains_wakeword, strip_wakewords

if TYPE_CHECKING:
    from modules.speech.xSpeechService import SpeechService

logger = logging.getLogger("speech.api")

_GATEWAY_BASE = "http://127.0.0.1:8080"


def _gw(path: str) -> str:
    return f"{_GATEWAY_BASE.rstrip('/')}/{path.lstrip('/')}"


def _barge_in_urls() -> tuple[str, ...]:
    return (
        _gw("/speak/stop"),
        _gw("/agent/speech/interrupt"),
        _gw("/speech/start"),
    )


def _notify_autonomy():
    try:
        requests.post(_gw("/autonomy/interaction"), timeout=0.1)
    except Exception:
        pass


def _push_interaction_event(event_type: str):
    try:
        requests.post(
            _gw("/interactions/event"),
            json={"type": event_type},
            timeout=0.1,
        )
    except Exception:
        pass

def _emit_speech_event(name: str):
    threading.Thread(target=_push_interaction_event, args=(name,), daemon=True).start()


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
        return {
            "listening": service.listening,
            "model_ready": getattr(service, "recognizer", None) is not None,
            "stt_suppressed": bool(getattr(service, "is_stt_suppressed", lambda: False)()),
        }

    last: dict | None = {"text": None, "language": getattr(service, "source_language", "tr"), "ts": 0.0}
    last_nonempty_text = ""
    last_partial_text = ""
    last_partial_ts = 0.0
    speaking = False
    speaking_lock = Lock()

    def _mark_speaking(active: bool) -> bool:
        nonlocal speaking
        with speaking_lock:
            if active:
                if speaking:
                    return False
                speaking = True
                return True
            if not speaking:
                return False
            speaking = False
            return True

    def _schedule_speech_end(delay: float = 0.5):
        def _end():
            if _mark_speaking(False):
                _emit_speech_event("speech.end")
        timer = Timer(delay, _end)
        timer.daemon = True
        timer.start()

    def _cb(r):
        nonlocal last, last_partial_text, last_partial_ts, last_nonempty_text
        if hasattr(service, "is_stt_suppressed") and service.is_stt_suppressed():
            return
        text = (r.text or "").strip()
        language = getattr(service, "source_language", "tr")
        if r.is_final and hasattr(service, "finalize_stt"):
            text, language = service.finalize_stt(text or last_nonempty_text)
        if text:
            last_nonempty_text = text
        if text and contains_wakeword(text):
            remainder = strip_wakewords(text)
            if r.is_final or len(remainder.split()) < 2:
                threading.Thread(target=_barge_in_for_wakeword, daemon=True).start()
        last = {
            "text": text or last_nonempty_text or None,
            "final": r.is_final,
            "confidence": r.confidence,
            "language": language,
            "ts": time.time(),
        }
        # STT logs should be visible even when downstream modules (e.g. ollama)
        # are offline; log both partial and final recognition results.
        if r.is_final:
            if text:
                logger.info("STT >>> %s (lang=%s)", text, language)
            else:
                logger.debug("stt final empty")
            last_partial_text = ""
        else:
            now = time.time()
            # Throttle partial logs to avoid log spam but keep visibility.
            if text and (text != last_partial_text or (now - last_partial_ts) >= 0.35):
                logger.info("STT (partial) >>> %s", text)
                last_partial_text = text
                last_partial_ts = now

        if r.is_final and (text or last_nonempty_text):
            threading.Thread(target=_notify_autonomy, daemon=True).start()
            if _mark_speaking(True):
                _emit_speech_event("speech.start")
            _schedule_speech_end()

    @router.post("/speech/start")
    async def start():
        was_listening = service.listening
        logger.info("speech start requested (was_listening=%s)", was_listening)
        if hasattr(service, "clear_utterance_buffer"):
            service.clear_utterance_buffer()
        service.start_background(on_result=_cb)
        logger.info("speech start handled (listening=%s)", service.listening)
        if not was_listening:
            _emit_speech_event("speech.start")
        return {"ok": True, "listening": service.listening}

    @router.post("/speech/stop")
    async def stop():
        service.stop()
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
