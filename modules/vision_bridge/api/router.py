from __future__ import annotations
from fastapi import APIRouter
from typing import Optional

try:
    from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService  # type: ignore
except Exception:
    from ..services.stub import xArduinoSerialService  # type: ignore

# Shared singleton to avoid re-creating serial per request (fallback only)
_ardu_singleton: Optional[xArduinoSerialService] = None

def _get_or_create_ardu() -> xArduinoSerialService:
    global _ardu_singleton
    if _ardu_singleton is None:
        from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService  # type: ignore
        _ardu_singleton = xArduinoSerialService()
        _ardu_singleton.start()
    return _ardu_singleton


def get_router(ardu: Optional[xArduinoSerialService] = None) -> APIRouter:
    r = APIRouter(prefix="/vision")

    @r.post("/track")
    def track(head_tilt: float, head_pan: float, drive: int | None = None):
        svc = ardu or _get_or_create_ardu()
        payload = {"cmd": "track", "head_tilt": head_tilt, "head_pan": head_pan}
        if drive is not None:
            payload["drive"] = int(drive)
        try:
            resp = svc.request(payload, timeout=1.0)
            return {"ok": bool(resp.get("ok", False)), "resp": resp}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return r
