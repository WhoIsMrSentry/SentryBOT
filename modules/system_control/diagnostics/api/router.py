from __future__ import annotations

import threading
from typing import Any, Dict

from fastapi import APIRouter

from modules.common.url_utils import resolve_gateway_base_url
from ..services.selftest import run_http_checks_async


def get_router(cfg: Dict[str, Any]) -> APIRouter:
    r = APIRouter(prefix="/diagnostics", tags=["diagnostics"])
    report_lock = threading.Lock()
    last_report: Dict[str, Any] = {"ok": True, "note": "not_run_yet"}

    def _build_checks() -> Dict[str, Any]:
        checks_cfg = cfg.get("checks", {}) if isinstance(cfg.get("checks", {}), dict) else {}
        # Backward compatible: bool map support.
        default_paths: Dict[str, tuple[str, str]] = {
            "camera": ("GET", "/camera/healthz"),
            "arduino": ("GET", "/arduino/healthz"),
            "neopixel": ("GET", "/neopixel/healthz"),
            "speech": ("GET", "/speech/status"),
            "speak": ("GET", "/speak/status"),
            "wakeword": ("GET", "/wakeword/status"),
            "oled_faces": ("GET", "/oled_faces/healthz"),
            "agent_core": ("GET", "/agent/healthz"),
            "autonomy": ("GET", "/autonomy/state"),
        }

        out: Dict[str, Any] = {}
        for name, value in checks_cfg.items():
            if isinstance(value, bool):
                if value and name in default_paths:
                    method, path = default_paths[name]
                    out[name] = {"enabled": True, "method": method, "path": path}
                continue
            if isinstance(value, dict):
                out[name] = value
        if not out:
            for name, (method, path) in default_paths.items():
                out[name] = {"enabled": True, "method": method, "path": path}
        return out

    @r.get("/healthz")
    def healthz():
        return {"ok": True}

    @r.post("/run")
    async def run():
        nonlocal last_report
        port = int(cfg.get("gateway_port", 8080))
        base = resolve_gateway_base_url(cfg, port=port)
        thresholds = cfg.get("thresholds", {}) if isinstance(cfg.get("thresholds", {}), dict) else {}
        report_data = await run_http_checks_async(
            base_url=base,
            checks=_build_checks(),
            default_timeout_ms=int(thresholds.get("default_timeout_ms", 1000)),
            default_latency_warn_ms=int(thresholds.get("default_latency_warn_ms", 600)),
            self_heal=cfg.get("self_heal", {}),
            notify=cfg.get("notify", {}),
            system_checks=cfg.get("system_checks", {"enabled": True}),
        )
        with report_lock:
            last_report = report_data
        return report_data

    @r.get("/report")
    def report():
        with report_lock:
            return dict(last_report)

    return r
