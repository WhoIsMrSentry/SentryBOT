from __future__ import annotations
from typing import Dict, Any
from fastapi import APIRouter

from ..services.system import read_system_snapshot
from ..services.i2c import scan as i2c_scan
from ..services.gpio import GPIO


def get_router(cfg: Dict[str, Any]) -> APIRouter:
    r = APIRouter(prefix="/hardware", tags=["hardware"])

    @r.get("/healthz")
    def healthz():
        snap = read_system_snapshot().to_dict()
        return {"ok": True, "system": snap}

    @r.get("/system")
    def system():
        return read_system_snapshot().to_dict()

    @r.get("/i2c/scan")
    def i2c_scan_endpoint():
        bus = int(cfg.get("i2c", {}).get("bus", 1))
        return {"bus": bus, "addresses": [hex(a) for a in i2c_scan(bus)]}

    @r.get("/gpio/info")
    def gpio_info():
        mode = str(cfg.get("gpio", {}).get("mode", "bcm"))
        return GPIO(mode).info()

    return r
