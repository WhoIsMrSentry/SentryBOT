"""MCP client: stdio transport handshake, tools list/call, service + router."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from modules.mcp_client.services.stdio_process import (
    RemoteError,
    RequestTimeout,
    ServerNotFound,
    StdioMcpConnection,
)
from modules.mcp_client.xMcpClientService import McpClientService

REPO_ROOT = Path(__file__).resolve().parents[3]
ECHO_SCRIPT = REPO_ROOT / "modules" / "mcp_client" / "examples" / "echo_server.py"

SLEEPER = [sys.executable, "-c", "import time; time.sleep(5)"]


def _echo_spec(timeout_s: float = 10.0, init_timeout_s: float = 10.0) -> dict:
    return {
        "mcp_client": {
            "enabled": True,
            "client": {
                "name": "test-client",
                "version": "0.0.1",
                "protocol_version": "2024-11-05",
                "request_timeout_s": timeout_s,
                "init_timeout_s": init_timeout_s,
            },
            "servers": [
                {
                    "name": "echo-demo",
                    "enabled": True,
                    "autostart": False,
                    "command": [sys.executable],
                    "args": [str(ECHO_SCRIPT)],
                }
            ],
        }
    }


@pytest.fixture()
def svc():
    svc = McpClientService(_echo_spec())
    yield svc
    svc.stop()


# ---- transport level ----------------------------------------------------

def test_handshake_and_roundtrip():
    conn = StdioMcpConnection(
        name="t",
        command=[sys.executable, str(ECHO_SCRIPT)],
        client_name="t-client",
        client_version="0.1",
        init_timeout_s=10.0,
        request_timeout_s=10.0,
    )
    info = conn.handshake()
    assert info.get("name") == "echo-demo"
    tools = conn.tools()
    names = {t["name"] for t in tools}
    assert {"echo", "add"} <= names
    out = conn.call("echo", {"text": "merhaba"})
    assert "echo:merhaba" in str(out.get("content"))
    res = conn.request("tools/call", {"name": "add", "arguments": {"a": 2, "b": 3}})
    texts = [c.get("text") for c in res.get("content", []) if isinstance(c, dict)]
    assert texts and texts[0] == "5"
    bad = conn.call("add", {"a": "x", "b": 1})
    assert bool(bad.get("isError")) is True
    assert conn.ping() is True
    conn.stop()


def test_init_timeout_against_silent_process():
    conn = StdioMcpConnection(
        name="sleeper",
        command=SLEEPER,
        init_timeout_s=0.6,
        request_timeout_s=1.0,
    )
    conn.start()
    with pytest.raises(RequestTimeout):
        conn.handshake()
    conn.stop()


def test_stderr_and_stop_cleanup():
    conn = StdioMcpConnection(
        name="sleeper2",
        command=SLEEPER,
        init_timeout_s=1.0,
        request_timeout_s=1.0,
    )
    conn.start()
    conn.stop()
    assert conn.alive is False
    assert conn.proc is None


# ---- service level ------------------------------------------------------

def test_service_call_and_errors(svc):
    out = svc.call("echo-demo", "echo", {"text": "ping"})
    assert out["ok"] is True and out["is_error"] is False and "echo:ping" in out["text"]

    out = svc.call("echo-demo", "add", {"a": 4, "b": 1})
    assert out["text"] == "5"

    out = svc.call("echo-demo", "nope", {})
    assert out["is_error"] is True and "unknown_tool:nope" in out["text"]

    with pytest.raises(ServerNotFound):
        svc.call("ghost", "echo", {})

    tools = svc.tools("echo-demo")
    assert tools["ok"] is True and len(tools["tools"]) == 2

    status = svc.status()
    entry = [s for s in status["servers"] if s["name"] == "echo-demo"][0]
    assert entry["connected"] is True
    assert entry["server_info"].get("name") == "echo-demo"


def test_service_restart_and_stop(svc):
    res = svc.restart("echo-demo")
    assert res["ok"] is True and res["server"] == "echo-demo"
    assert (res["server_info"] or {}).get("name") == "echo-demo"
    assert svc.stop()["stopped"] == ["echo-demo"]
    entry = [s for s in svc.status()["servers"] if s["name"] == "echo-demo"][0]
    assert entry["connected"] is False


# ---- router level -------------------------------------------------------

def _router_app():
    from fastapi import FastAPI

    from modules.mcp_client.api.router import get_router

    svc = McpClientService(_echo_spec())
    app = FastAPI()
    app.include_router(get_router(svc))
    return svc, app


def test_router_endpoints():
    from fastapi.testclient import TestClient

    svc, app = _router_app()
    try:
        client = TestClient(app)
        assert client.get("/mcp_client/healthz").json() == {"ok": True}
        status = client.get("/mcp_client/status").json()
        assert status["servers"][0]["name"] == "echo-demo"
        tools = client.get("/mcp_client/tools", params={"refresh": True}).json()
        assert tools["servers"]["echo-demo"][0]["name"] == "echo"
        resp = client.post("/mcp_client/call", json={"server": "echo-demo", "tool": "echo", "arguments": {"text": "hi"}})
        assert resp.status_code == 200 and "echo:hi" in resp.json()["text"]
        assert client.post("/mcp_client/call", json={"server": "ghost", "tool": "x"}).status_code == 404
    finally:
        svc.stop()
