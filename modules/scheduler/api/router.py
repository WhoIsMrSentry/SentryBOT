from __future__ import annotations
from typing import Dict, Any
from fastapi import APIRouter


def get_router(cfg: Dict[str, Any]) -> APIRouter:
    r = APIRouter(prefix="/scheduler", tags=["scheduler"])

    @r.get("/healthz")
    def healthz():
        return {"ok": True}

    @r.get("/jobs")
    def jobs():
        return cfg.get("jobs", [])

    return r
