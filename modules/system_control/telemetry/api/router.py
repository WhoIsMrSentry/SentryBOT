from __future__ import annotations
from typing import Dict, Any
from fastapi import APIRouter, Response

from ..services.metrics import REGISTRY, read_system_snapshot


def _refresh_host_gauges() -> None:
    try:
        snap = read_system_snapshot()
        if snap.cpu_temp_c is not None:
            REGISTRY.gauge("sentrybot_cpu_temp_c", "CPU temperature Celsius").set(float(snap.cpu_temp_c))
        if snap.cpu_load_1m is not None:
            REGISTRY.gauge("sentrybot_cpu_load_1m", "CPU load average 1m").set(float(snap.cpu_load_1m))
    except Exception:
        pass


def get_router(cfg: Dict[str, Any]) -> APIRouter:
    r = APIRouter(prefix="/telemetry", tags=["telemetry"])

    @r.get("/healthz")
    def healthz():
        return {"ok": True}

    @r.get("/metrics")
    def metrics() -> Response:
        _refresh_host_gauges()
        return Response(REGISTRY.render_prometheus(), media_type="text/plain; version=0.0.4")

    @r.post("/events")
    def events(ev: Dict[str, Any]):
        t = str(ev.get("type", "unknown")).replace(" ", "_").replace("-", "_")
        safe_name = "".join(c for c in t if c.isalnum() or c == "_")[:32] or "unknown"
        REGISTRY.counter("events_total").inc(1)
        REGISTRY.counter(f"event_{safe_name}_total").inc(1)
        return {"ok": True}

    return r
