from __future__ import annotations

import math
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException

try:
    from ..services.runner import EarRunner
except ImportError:
    from modules.expression.piservo.services.runner import EarRunner  # type: ignore


def _validate_angle(name: str, val: float, min_deg: float, max_deg: float) -> float:
    if not math.isfinite(val):
        raise HTTPException(status_code=400, detail=f"{name} must be finite")
    if val < min_deg or val > max_deg:
        raise HTTPException(
            status_code=400,
            detail=f"{name} must be in [{min_deg}, {max_deg}]",
        )
    return float(val)


def get_router(runner: EarRunner) -> APIRouter:
    r = APIRouter(prefix="/piservo", tags=["piservo"], responses={404: {"description": "Not found"}})

    @r.get("/healthz", tags=["piservo"], summary="Healthz")
    def healthz():
        return {
            "ok": runner.is_healthy(),
            "backend": runner.backend_name,
            "error": runner.last_error,
        }

    @r.get("/status", tags=["piservo"], summary="Status")
    def status():
        return runner.status()

    @r.post("/set", tags=["piservo"], summary="Set Angles")
    def set_angles(left: float, right: float):
        l_val = _validate_angle("left", left, runner.left.cfg.min_deg, runner.left.cfg.max_deg)
        r_val = _validate_angle("right", right, runner.right.cfg.min_deg, runner.right.cfg.max_deg)
        out_l, out_r = runner.set_angles(l_val, r_val)
        return {"ok": True, "left": out_l, "right": out_r}

    @r.post("/emotion", tags=["piservo"], summary="Emotion")
    def emotion(name: Optional[str] = None, body: Optional[dict[str, Any]] = Body(default=None)):
        target_name = name if name is not None else (body or {}).get("name")
        if not target_name or not str(target_name).strip():
            raise HTTPException(status_code=400, detail="emotion name is required")
        out_l, out_r = runner.emotion(str(target_name))
        return {"ok": True, "left": out_l, "right": out_r}

    @r.post("/gesture", tags=["piservo"], summary="Gesture")
    def gesture(name: str):
        try:
            out_l, out_r = runner.gesture(name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "left": out_l, "right": out_r}

    @r.post("/reflex", tags=["piservo"], summary="Acoustic Reflex")
    def reflex(angle: float, energy: float = 1.0):
        if not math.isfinite(angle):
            raise HTTPException(status_code=400, detail="angle must be finite")
        if not math.isfinite(energy) or energy < 0.0:
            raise HTTPException(status_code=400, detail="energy must be finite and >= 0")
        left, right = runner.reflex(angle, energy)
        return {"ok": True, "left": left, "right": right}

    @r.post("/event", tags=["piservo"], summary="Event")
    def event(kind: str):
        try:
            out_l, out_r = runner.event(kind)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "left": out_l, "right": out_r}

    return r
