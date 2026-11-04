from __future__ import annotations

from fastapi import FastAPI
from modules.mcp_client.xMcpClientService import McpClientService
from modules.mcp_client.api.router import get_router


def test_mcp_client_service_smoke():
    svc = McpClientService({})
    assert svc is not None
    assert svc.client_name == "sentrybot-mcp-client"


def test_mcp_client_router_smoke():
    svc = McpClientService({})
    router = get_router(svc)
    app = FastAPI()
    app.include_router(router)
    assert app is not None

