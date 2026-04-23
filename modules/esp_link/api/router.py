from __future__ import annotations

from fastapi import APIRouter, HTTPException
from typing import Dict, Any

try:
    from ..xEspLinkService import xEspLinkService
except Exception:
    from modules.esp_link.xEspLinkService import xEspLinkService  # type: ignore


def get_router(svc: xEspLinkService) -> APIRouter:
    r = APIRouter(prefix="/esp", tags=["esp_link"])

    @r.get("/healthz")
    def healthz() -> Dict[str, Any]:
        try:
            data = svc.healthz()
            return {"ok": bool(data.get("ok", True)), "resp": data}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    @r.post("/send")
    def send(obj: Dict[str, Any]):
        try:
            return svc.send(obj)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @r.post("/request")
    def request(obj: Dict[str, Any], timeout: float = 1.0):
        try:
            return svc.request(obj, timeout=timeout)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return r
