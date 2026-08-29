from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional
import httpx


class AsyncGatewayProbe:
    """Non-blocking HTTP probe for SentryBOT Gateway & Modules."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000") -> None:
        self.base_url = base_url.rstrip("/")
        self.online = False
        self.last_probe_time = 0.0
        self.last_probe_ms = 0.0
        self.health_data: Dict[str, Any] = {}
        self.camera_data: Dict[str, Any] = {}
        self.expression_data: Dict[str, Any] = {}
        self.companion_data: Dict[str, Any] = {}
        self.error_message: Optional[str] = None

    async def probe_all(self) -> bool:
        """Probe all key endpoints with short timeouts."""
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=0.6) as client:
            try:
                # 1. Main health check
                resp = await client.get(f"{self.base_url}/runtime_console/healthz")
                self.last_probe_ms = (time.perf_counter() - t0) * 1000.0
                if resp.status_code == 200:
                    self.online = True
                    self.health_data = resp.json()
                    self.error_message = None
                else:
                    # Try state fallback
                    resp_state = await client.get(f"{self.base_url}/state/get")
                    if resp_state.status_code == 200:
                        self.online = True
                        self.health_data = resp_state.json()
                        self.error_message = None
                    else:
                        self.online = False
                        self.error_message = f"Gateway returned HTTP {resp.status_code}"
            except Exception as exc:
                self.online = False
                self.last_probe_ms = (time.perf_counter() - t0) * 1000.0
                self.error_message = "Gateway offline / unreachable"
                return False

            # If gateway is online, fetch subsystem statuses
            if self.online:
                try:
                    r_cam = await client.get(f"{self.base_url}/camera/status")
                    if r_cam.status_code == 200:
                        self.camera_data = r_cam.json()
                except Exception:
                    pass

                try:
                    r_exp = await client.get(f"{self.base_url}/expression/state")
                    if r_exp.status_code == 200:
                        self.expression_data = r_exp.json()
                except Exception:
                    pass

                try:
                    r_comp = await client.get(f"{self.base_url}/autonomy/status")
                    if r_comp.status_code == 200:
                        self.companion_data = r_comp.json()
                except Exception:
                    pass

        return self.online
