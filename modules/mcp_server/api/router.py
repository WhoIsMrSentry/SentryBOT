from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..xMcpServerService import xMcpServerService


def get_router(svc: xMcpServerService) -> APIRouter:
    r = APIRouter(prefix="/mcp", tags=["mcp-server"])

    @r.get("/healthz")
    def healthz():
        return {"ok": svc.is_available()}

    @r.get("/status")
    def status():
        return svc.status()

    @r.get("/tools")
    def tools():
        return {"ok": True, "tools": svc.list_tools()}

    @r.get("/resources")
    def resources():
        return {"ok": True, "resources": svc.list_resources()}

    @r.get("/resources/read")
    def read_resource(uri: str = Query(...)):
        try:
            return {"ok": True, **svc.read_resource(uri)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return r
