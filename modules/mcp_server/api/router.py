from fastapi import APIRouter

from ..xMcpServerService import xMcpServerService


def get_router(svc: xMcpServerService) -> APIRouter:
    r = APIRouter(prefix="/mcp")

    @r.get("/healthz")
    def healthz():
        return {"ok": svc.is_available()}

    @r.get("/status")
    def status():
        return svc.status()

    @r.get("/tools")
    def tools():
        return {"ok": True, "tools": svc.list_tools()}

    return r
