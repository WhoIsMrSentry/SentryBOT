from __future__ import annotations
from fastapi import APIRouter, Query
from typing import Optional

try:
    from ..xAnimateService import xAnimateService
except Exception:
    from modules.animate.xAnimateService import xAnimateService  # type: ignore


def get_router(anim: xAnimateService) -> APIRouter:
    r = APIRouter(prefix="/animate")

    @r.get("/list")
    def list_animations():
        return {"ok": True, "animations": anim.list()}

    @r.post("/run")
    def run(name: str, speed: float = 1.0, loop: bool = Query(False)):
        # run blocking in this thread for simplicity (caller should spawn)
        anim.run(name, speed=speed, loop=loop)
        return {"ok": True}

    @r.post("/stop")
    def stop():
        anim.stop_run()
        return {"ok": True}

    return r
