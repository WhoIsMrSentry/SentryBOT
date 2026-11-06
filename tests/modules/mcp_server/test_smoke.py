from __future__ import annotations

from fastapi import FastAPI
from modules.mcp_server.xMcpServerService import xMcpServerService
from modules.mcp_server.api.router import get_router


def test_mcp_server_service_smoke():
    svc = xMcpServerService({})
    assert svc is not None


def test_mcp_server_router_smoke():
    svc = xMcpServerService({})
    router = get_router(svc)
    app = FastAPI()
    app.include_router(router)
    assert app is not None

