from __future__ import annotations
from typing import Dict, Any
from fastapi import APIRouter, Response

from ..services.metrics import REGISTRY


def get_router(cfg: Dict[str, Any]) -> APIRouter:
    r = APIRouter(prefix="/telemetry", tags=["telemetry"])

    @r.get("/healthz")
    def healthz():
        return {"ok": True}

    @r.get("/metrics")
    def metrics() -> Response:
        return Response(REGISTRY.render_prometheus(), media_type="text/plain; version=0.0.4")

    @r.post("/events")
    def events(ev: Dict[str, Any]):
        # minimal counter for event types
        t = ev.get("type", "unknown")
        REGISTRY.counter(f"events_total").inc(1)
        REGISTRY.counter(f"event_{t}_total").inc(1)
        return {"ok": True}

    return r
