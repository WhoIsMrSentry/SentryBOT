from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, Optional
import httpx


def resolve_base_url(explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit.rstrip("/")
    env = str(os.environ.get("SENTRY_GATEWAY_URL", "")).strip().rstrip("/")
    if env:
        return env
    try:
        from modules.gateway.url import resolve_gateway_base_url

        return resolve_gateway_base_url(port=8080)
    except Exception:
        return "http://127.0.0.1:8080"


class AsyncGatewayProbe:
    """Non-blocking HTTP probe for SentryBOT Gateway, State, Autonomy & Modules."""

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = resolve_base_url(base_url)
        self.online = False
        self.last_probe_time = 0.0
        self.last_probe_ms = 0.0
        self.health_data: Dict[str, Any] = {}
        self.state_data: Dict[str, Any] = {}
        self.camera_data: Dict[str, Any] = {}
        self.expression_data: Dict[str, Any] = {}
        self.companion_data: Dict[str, Any] = {}
        self.status_data: Dict[str, Any] = {}
        self.diagnostics_data: Dict[str, Any] = {}
        self.error_message: Optional[str] = None

    async def probe_all(self) -> bool:
        """Probe gateway liveness and fetch live subsystem telemetry concurrently."""
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=0.8) as client:
            # 1. Probe primary health/status
            try:
                resp = await client.get(f"{self.base_url}/healthz")
                if resp.status_code != 200:
                    resp = await client.get(f"{self.base_url}/runtime_console/healthz")
                self.last_probe_ms = (time.perf_counter() - t0) * 1000.0

                if resp.status_code == 200:
                    self.online = True
                    self.health_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"ok": True}
                    self.error_message = None
                else:
                    self.online = False
                    self.error_message = f"Gateway HTTP {resp.status_code}"
                    return False
            except Exception as exc:
                self.online = False
                self.last_probe_ms = (time.perf_counter() - t0) * 1000.0
                self.error_message = "Gateway offline / unreachable"
                return False

            # 2. Concurrently fetch all live telemetry sub-resources
            async def _get(path: str) -> Optional[Dict[str, Any]]:
                try:
                    r = await client.get(f"{self.base_url}{path}")
                    if r.status_code == 200:
                        return r.json()
                except Exception:
                    pass
                return None

            results = await asyncio.gather(
                _get("/state/get"),
                _get("/autonomy/needs"),
                _get("/autonomy/goal"),
                _get("/camera/status"),
                _get("/expression/state"),
                _get("/status"),
                _get("/diagnostics/report"),
                return_exceptions=True,
            )

            state_res = results[0] if isinstance(results[0], dict) else None
            needs_res = results[1] if isinstance(results[1], dict) else None
            goal_res = results[2] if isinstance(results[2], dict) else None
            cam_res = results[3] if isinstance(results[3], dict) else None
            exp_res = results[4] if isinstance(results[4], dict) else None
            stat_res = results[5] if isinstance(results[5], dict) else None
            diag_res = results[6] if isinstance(results[6], dict) else None

            if state_res:
                self.state_data = state_res
                self.health_data["state"] = state_res

            comp_combined = {}
            if needs_res:
                comp_combined.update(needs_res)
            if goal_res:
                comp_combined.update(goal_res)
            if comp_combined:
                self.companion_data = comp_combined

            if cam_res:
                self.camera_data = cam_res

            if exp_res:
                self.expression_data = exp_res

            if stat_res:
                self.status_data = stat_res

            if diag_res:
                self.diagnostics_data = diag_res

        self.last_probe_time = time.time()
        return self.online
