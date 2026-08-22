from __future__ import annotations
from fastapi import APIRouter
from typing import Optional

try:
    from ..services.runner import EarRunner
except Exception:
    from services.runner import EarRunner  # type: ignore


def get_router(runner: EarRunner) -> APIRouter:
    r = APIRouter(prefix="/piservo", tags=["piservo"], responses={404: {"description": "Not found"}})

    @r.get("/healthz", tags=["piservo"], summary="Healthz")
    def healthz():
        return {"ok": True}

    @r.post("/set", tags=["piservo"], summary="Set Angles")
    def set_angles(left: float, right: float):
        runner.set_angles(left, right)
        return {"ok": True}

    @r.post("/emotion", tags=["piservo"], summary="Emotion")
    def emotion(name: str):
        runner.emotion(name)
        return {"ok": True}

    @r.post("/gesture", tags=["piservo"], summary="Gesture")
    def gesture(name: str):
        runner.gesture(name)
        return {"ok": True}

    @r.post("/event", tags=["piservo"], summary="Event")
    def event(kind: str):
        runner.event(kind)
        return {"ok": True}

    return r
