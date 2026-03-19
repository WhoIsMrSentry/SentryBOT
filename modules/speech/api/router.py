from __future__ import annotations
from fastapi import APIRouter
import requests
import threading
import logging
import time
from threading import Timer, Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.speech.xSpeechService import SpeechService

logger = logging.getLogger("speech.api")

def _notify_autonomy():
    try:
        requests.post("http://localhost:8080/autonomy/interaction", timeout=0.1)
    except Exception:
        pass

def _push_interaction_event(event_type: str):
    try:
        requests.post(
            "http://localhost:8080/interactions/event",
            json={"type": event_type},
            timeout=0.1,
        )
    except Exception:
        pass

def _emit_speech_event(name: str):
    threading.Thread(target=_push_interaction_event, args=(name,), daemon=True).start()

def get_router(service: SpeechService) -> APIRouter:
    router = APIRouter()

    @router.get("/speech/status")
    async def status():
        return {"listening": service.listening}

    last: dict | None = {"text": None, "language": getattr(service, "source_language", "tr")}
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
        nonlocal last, last_partial_text, last_partial_ts
        last = {
            "text": r.text,
            "final": r.is_final,
            "confidence": r.confidence,
            "language": getattr(service, "source_language", "tr"),
        }
        # STT logs should be visible even when downstream modules (e.g. ollama)
        # are offline; log both partial and final recognition results.
        text = (r.text or "").strip()
        if r.is_final:
            if text:
                logger.info("stt final [%s]: %s (conf=%s)", last.get("language", "tr"), text, r.confidence)
            else:
                logger.debug("stt final empty")
            last_partial_text = ""
        else:
            now = time.time()
            # Throttle partial logs to avoid log spam but keep visibility.
            if text and (text != last_partial_text or (now - last_partial_ts) >= 0.35):
                logger.info("stt partial [%s]: %s", last.get("language", "tr"), text)
                last_partial_text = text
                last_partial_ts = now

        if r.is_final and r.text:
            threading.Thread(target=_notify_autonomy, daemon=True).start()
            if _mark_speaking(True):
                _emit_speech_event("speech.start")
            _schedule_speech_end()

    @router.post("/speech/start")
    async def start():
        was_listening = service.listening
        logger.info("speech start requested (was_listening=%s)", was_listening)
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

    return router
