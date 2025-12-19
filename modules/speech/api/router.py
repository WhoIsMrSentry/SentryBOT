from __future__ import annotations
from fastapi import APIRouter, Response
import requests
import threading
from threading import Timer, Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.speech.xSpeechService import SpeechService

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
        return {"listening": True}

    last: dict | None = {"text": None}
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
        nonlocal last
        last = {"text": r.text, "final": r.is_final, "confidence": r.confidence}
        if r.is_final and r.text:
            threading.Thread(target=_notify_autonomy, daemon=True).start()
            if _mark_speaking(True):
                _emit_speech_event("speech.start")
            _schedule_speech_end()

    @router.post("/speech/start")
    async def start():
        service.start_background(on_result=_cb)
        _emit_speech_event("speech.start")
        return {"ok": True}

    @router.post("/speech/stop")
    async def stop():
        service.stop()
        _emit_speech_event("speech.end")
        return {"ok": True}

    @router.get("/speech/last")
    async def last_result():
        return last or {}

    @router.get("/speech/direction")
    async def direction():
        angle = service.last_angle if hasattr(service, "last_angle") else None
        if angle is None:
            return Response(status_code=503)
        return {"angle": angle}

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
