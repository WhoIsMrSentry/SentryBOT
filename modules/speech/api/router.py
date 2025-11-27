from __future__ import annotations
from fastapi import APIRouter, Response
import requests
import threading

try:
    from ..xSpeechService import SpeechService
except Exception:
    from xSpeechService import SpeechService  # type: ignore

def _notify_autonomy():
    try:
        requests.post("http://localhost:8080/autonomy/interaction", timeout=0.1)
    except Exception:
        pass

def get_router(service: SpeechService) -> APIRouter:
    router = APIRouter()

    @router.get("/speech/status")
    async def status():
        return {"listening": True}

    last: dict | None = {"text": None}

    def _cb(r):
        nonlocal last
        last = {"text": r.text, "final": r.is_final, "confidence": r.confidence}
        if r.is_final and r.text:
            threading.Thread(target=_notify_autonomy, daemon=True).start()

    @router.post("/speech/start")
    async def start():
        service.start_background(on_result=_cb)
        return {"ok": True}

    @router.post("/speech/stop")
    async def stop():
        service.stop()
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
