from __future__ import annotations
from fastapi import APIRouter
from typing import TYPE_CHECKING
import asyncio
import logging

if TYPE_CHECKING:
    from modules.speak.xSpeakService import SpeakService


logger = logging.getLogger("speak.api")

def get_router(service: SpeakService) -> APIRouter:
    router = APIRouter()

    @router.get("/speak/status")
    async def status():
        return {"ready": True}

    @router.post("/speak/say")
    async def say(payload: dict):
        text = str(payload.get("text", "")).strip()
        engine = payload.get("engine")
        tone = payload.get("tone")
        if not text:
            return {"ok": False, "error": "text is empty"}
        try:
            # Offload blocking TTS to thread to avoid event loop freeze
            return await asyncio.to_thread(service.speak, text, engine=engine, tone=tone)
        except Exception as e:
            logger.exception("/speak/say failed")
            return {"ok": False, "error": repr(e)}

    @router.post("/speak/play")
    async def play(payload: dict):
        import base64
        data_b64 = payload.get("data")
        if not data_b64:
            return {"ok": False, "error": "data (base64 WAV) is required"}
        try:
            buf = base64.b64decode(data_b64)
            return service.play_wav(buf)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return router
