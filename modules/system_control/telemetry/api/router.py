from __future__ import annotations

from dataclasses import asdict
import logging
from typing import Any, Dict
from fastapi import APIRouter, Response

from ..services.metrics import REGISTRY, SystemSnapshot, read_system_snapshot

logger = logging.getLogger("telemetry.router")


def _refresh_host_gauges() -> SystemSnapshot | None:
    try:
        snap = read_system_snapshot()
        if snap.cpu_temp_c is not None:
            REGISTRY.gauge("sentrybot_cpu_temp_c", "CPU temperature Celsius").set(float(snap.cpu_temp_c))
        if snap.cpu_load_1m is not None:
            REGISTRY.gauge("sentrybot_cpu_load_1m", "CPU load average 1m").set(float(snap.cpu_load_1m))
        if getattr(snap, "mem_available_mb", None) is not None:
            REGISTRY.gauge("sentrybot_mem_available_mb", "Available RAM in MB").set(
                float(snap.mem_available_mb)
            )
        if getattr(snap, "disk_free_gb", None) is not None:
            REGISTRY.gauge("sentrybot_disk_free_gb", "Free disk space in GB").set(float(snap.disk_free_gb))
        if getattr(snap, "disk_used_pct", None) is not None:
            REGISTRY.gauge("sentrybot_disk_used_pct", "Disk usage percentage").set(float(snap.disk_used_pct))
        return snap
    except Exception as exc:
        logger.debug("host gauge refresh failed: %s", exc)
        return None


def _parse_latency(ev: Dict[str, Any]) -> float | None:
    raw = ev.get("latency_ms", ev.get("duration_ms"))
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        logger.debug("ignoring non-numeric event latency %r", raw)
        return None


def get_router(cfg: Dict[str, Any]) -> APIRouter:
    exporter_cfg = (cfg or {}).get("exporter", {})
    exporter_type = str(exporter_cfg.get("type", "builtin")).strip().lower() or "builtin"
    exporter_enabled = exporter_type != "none"

    r = APIRouter(prefix="/telemetry", tags=["telemetry"])

    @r.get("/healthz")
    def healthz() -> Dict[str, Any]:
        return {"ok": True, "exporter": exporter_type}

    @r.get("/metrics")
    def metrics() -> Response:
        if not exporter_enabled:
            return Response(
                "# exporter disabled (exporter.type=none)\n",
                status_code=503,
                media_type="text/plain; version=0.0.4",
            )
        _refresh_host_gauges()
        return Response(REGISTRY.render_prometheus(), media_type="text/plain; version=0.0.4")

    @r.get("/snapshot")
    def snapshot() -> Dict[str, Any]:
        snap = _refresh_host_gauges()
        return {
            "ok": True,
            "exporter": exporter_type,
            "host": asdict(snap) if snap is not None else {},
            **REGISTRY.snapshot(),
        }

    @r.post("/events")
    def events(ev: Dict[str, Any]) -> Dict[str, Any]:
        latency = _parse_latency(ev)
        metric_name = REGISTRY.record_event(ev.get("type", "unknown"), latency_ms=latency)
        return {"ok": True, "metric": metric_name}

    return r
