from fastapi import APIRouter, Body, HTTPException

from ..services.stdio_process import McpClientError, RequestTimeout, ServerNotFound
from ..xMcpClientService import McpClientService


def get_router(svc: McpClientService) -> APIRouter:
    r = APIRouter(prefix="/mcp_client")

    @r.get("/healthz")
    def healthz():
        return {"ok": svc.health()}

    @r.get("/status")
    def status():
        return svc.status()

    @r.post("/autostart")
    def autostart():
        return svc.connect_all_autostart()

    @r.post("/stop")
    def stop_all():
        return svc.stop()

    @r.get("/tools")
    def tools(refresh: bool = False):
        try:
            return svc.tools(refresh=refresh)
        except McpClientError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @r.get("/tools/{server}")
    def tools_of(server: str, refresh: bool = False):
        try:
            return svc.tools(server, refresh=refresh)
        except ServerNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except McpClientError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @r.post("/call")
    def call(server: str = Body(...), tool: str = Body(...), arguments: dict = Body(default=None)):
        try:
            return svc.call(server, tool, arguments or {})
        except ServerNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except RequestTimeout as exc:
            raise HTTPException(status_code=504, detail=str(exc))
        except McpClientError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @r.post("/restart/{server}")
    def restart(server: str):
        try:
            return svc.restart(server)
        except ServerNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except McpClientError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @r.post("/stop/{server}")
    def stop(server: str):
        return svc.stop(server)

    return r
