from __future__ import annotations
from typing import Dict, Any
from fastapi import APIRouter

from ..services.camera_calib import suggest_checkerboard
from ..services.servo_calib import sweep_params


def get_router(cfg: Dict[str, Any]) -> APIRouter:
    r = APIRouter(prefix="/calib", tags=["calibration"])

    @r.get("/healthz")
    def healthz():
        return {"ok": True}

    @r.get("/camera/checkerboard")
    def checker(cols: int = 9, rows: int = 6, square_mm: float = 25.0):
        return suggest_checkerboard(cols, rows, square_mm)

    @r.get("/servo/sweep")
    def servo_sweep():
        return sweep_params()

    return r
