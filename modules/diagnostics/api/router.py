from __future__ import annotations
from typing import Dict, Any
from fastapi import APIRouter

from ..services.selftest import run_http_checks


def get_router(cfg: Dict[str, Any]) -> APIRouter:
    r = APIRouter(prefix="/diagnostics", tags=["diagnostics"])

    @r.get("/healthz")
    def healthz():
        return {"ok": True}

    @r.post("/run")
    def run():
        port = int(cfg.get("gateway_port", 8080))
        base = f"http://127.0.0.1:{port}"
        checks: Dict[str, tuple[str, str]] = {
            "camera": ("GET", "/camera/healthz"),
            "arduino": ("GET", "/arduino/healthz"),
            "neopixel": ("GET", "/neopixel/healthz"),
            "speech": ("GET", "/speech/status"),
            "speak": ("GET", "/speak/status"),
        }
        return run_http_checks(base, checks)

    @r.get("/report")
    def report():
        # For now just alias to run
        return run()

    return r
