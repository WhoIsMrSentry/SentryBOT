from __future__ import annotations
from fastapi import APIRouter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.voice.wakeword.xWakewordService import WakewordService


def get_router(service: "WakewordService") -> APIRouter:
    router = APIRouter()

    @router.get("/wakeword/healthz")
    async def healthz():
        return {"ok": True}

    @router.get("/wakeword/status")
    async def status():
        return service.status()

    @router.post("/wakeword/start")
    async def start():
        service.start_background()
        return {"ok": True, "listening": service.listening}

    @router.post("/wakeword/stop")
    async def stop():
        service.stop()
        return {"ok": True, "listening": service.listening}

    return router
