from __future__ import annotations
from fastapi import APIRouter
from typing import Optional

try:
    from ..services.runner import EarRunner
except Exception:
    from services.runner import EarRunner  # type: ignore


def get_router(runner: EarRunner) -> APIRouter:
    r = APIRouter(prefix="/piservo")

    @r.get("/healthz")
    def healthz():
        return {"ok": True}

    @r.post("/set")
    def set_angles(left: float, right: float):
        runner.set_angles(left, right)
        return {"ok": True}

    @r.post("/emotion")
    def emotion(name: str):
        runner.emotion(name)
        return {"ok": True}

    @r.post("/gesture")
    def gesture(name: str):
        runner.gesture(name)
        return {"ok": True}

    @r.post("/event")
    def event(kind: str):
        runner.event(kind)
        return {"ok": True}

    return r
