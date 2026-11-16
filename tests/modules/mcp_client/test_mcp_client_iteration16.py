"""Iteration 16 tests for modules/mcp_client hardening and lifecycle."""
from __future__ import annotations

import asyncio
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.common.config_loader import clear_agent_config_cache
from modules.mcp_client.config_loader import load_config
from modules.mcp_client.services.stdio_process import (
    RequestTimeout,
    StdioMcpConnection,
    TransportError,
)
from modules.mcp_client.xMcpClientService import McpClientService, _parse_command

_ECHO_SERVER = str(Path(__file__).resolve().parents[3] / "modules" / "mcp_client" / "examples" / "echo_server.py")


def _echo_cmd() -> list[str]:
    return [sys.executable, _ECHO_SERVER]


def _make_cfg(**client_overrides):
    client_cfg = {
        "name": "sentrybot-mcp-client",
        "version": "0.1.0",
        "init_timeout_s": 5.0,
        "request_timeout_s": 5.0,
    }
    client_cfg.update({k: v for k, v in client_overrides.items() if k in {"base_backoff_s", "max_backoff_s", "circuit_threshold", "init_timeout_s", "request_timeout_s"}})
    return {
        "mcp_client": {
            "enabled": client_overrides.get("enabled", True),
            "client": client_cfg,
            "servers": client_overrides.get("servers", []),
        }
    }


def _srv_status(svc: McpClientService, name: str) -> dict:
    return next(s for s in svc.status()["servers"] if s["name"] == name)


def test_config_loader_agent_override_and_bind_env(tmp_path, monkeypatch):
    cfg_file = tmp_path / "mcp_client.yml"
    cfg_file.write_text("mcp_client:\n  enabled: false\n  host: 127.0.0.1\n  port: 8765\n  servers: []\n", encoding="utf-8")
    agent_cfg = tmp_path / "agent.yaml"
    agent_cfg.write_text("mcp_client:\n  enabled: true\n  client:\n    circuit_threshold: 4\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_CFG", str(agent_cfg))
    monkeypatch.setenv("MCP_CLIENT_HOST", "0.0.0.0")
    clear_agent_config_cache()
    try:
        cfg = load_config(str(cfg_file))
        sec = cfg["mcp_client"]
        assert sec["enabled"] is True
        assert sec["client"]["circuit_threshold"] == 4
        assert sec["server"]["host"] == "0.0.0.0"
    finally:
        clear_agent_config_cache()


def test_parse_command_string_and_disabled_guards():
    assert _parse_command("python") == ["python"]
    assert _parse_command("python -u server.py --port 9000") == [
        "python",
        "-u",
        "server.py",
        "--port",
        "9000",
    ]
    assert _parse_command(["python", "-u"]) == ["python", "-u"]

    svc = McpClientService(
        _make_cfg(
            enabled=False,
            servers=[{"name": "echo", "command": _echo_cmd(), "autostart": True}],
        )
    )
    try:
        res = svc.connect_all_autostart()
        assert res["enabled"] is False
        assert svc._conns == {}
        assert svc.select_relevant_tools("echo") == []
        with pytest.raises(TransportError):
            svc.tools("echo")
        with pytest.raises(TransportError):
            svc.call("echo", "echo", {"text": "hi"})
        with pytest.raises(TransportError):
            svc.restart("echo")
    finally:
        svc.stop()


def _run_safe(fn, err_holder):
    try:
        fn()
    except Exception as exc:
        err_holder.append(exc)


def test_per_server_connect_locks_do_not_block_status_or_other_servers(monkeypatch):
    svc = McpClientService(
        _make_cfg(
            enabled=True,
            servers=[
                {"name": "slow", "command": _echo_cmd(), "autostart": False},
                {"name": "fast", "command": _echo_cmd(), "autostart": False},
            ],
        )
    )
    slow_started = threading.Event()
    release_slow = threading.Event()
    real_conn = StdioMcpConnection

    class BlockingConn(real_conn):
        def handshake(self):
            if getattr(self, "_is_slow", False):
                slow_started.set()
                assert release_slow.wait(timeout=5.0)
            return super().handshake()

    def tagged_conn(name, *args, **kwargs):
        conn = BlockingConn(name, *args, **kwargs)
        conn._is_slow = (name == "slow")
        return conn

    monkeypatch.setattr("modules.mcp_client.xMcpClientService.StdioMcpConnection", tagged_conn)

    err_holder = []
    t_slow = threading.Thread(target=lambda: _run_safe(lambda: svc.tools("slow"), err_holder))
    t_slow.start()
    try:
        assert slow_started.wait(timeout=3.0)

        t0 = time.monotonic()
        st = svc.status()
        assert (time.monotonic() - t0) < 0.8
        names = {s["name"] for s in st["servers"]}
        assert {"slow", "fast"} <= names

        fast_res = svc.tools("fast")
        assert fast_res["ok"] is True
        assert isinstance(fast_res["tools"], list)
    finally:
        release_slow.set()
        t_slow.join(timeout=5.0)
        svc.stop()
    assert not err_holder


def test_stdio_eof_fails_pending_immediately_and_timeout_cleans_zombie():
    eof_script = (
        "import sys, json\n"
        "for line in sys.stdin:\n"
        "    msg = json.loads(line)\n"
        "    if msg.get('method') == 'initialize':\n"
        "        sys.stdout.write(json.dumps({'jsonrpc':'2.0','id':msg['id'],'result':{'capabilities':{}}})+'\\n')\n"
        "        sys.stdout.flush()\n"
        "    elif msg.get('method') == 'tools/list':\n"
        "        sys.exit(0)\n"
    )
    conn_eof = StdioMcpConnection("eof_srv", [sys.executable, "-c", eof_script], init_timeout_s=5.0)
    conn_eof.start()
    conn_eof.handshake()
    t0 = time.monotonic()
    with pytest.raises(TransportError):
        conn_eof.request("tools/list", timeout=10.0)
    assert (time.monotonic() - t0) < 3.0
    assert conn_eof.alive is False
    conn_eof.stop()

    hang_script = (
        "import sys, json, time\n"
        "for line in sys.stdin:\n"
        "    msg = json.loads(line)\n"
        "    if msg.get('method') == 'initialize':\n"
        "        sys.stdout.write(json.dumps({'jsonrpc':'2.0','id':msg['id'],'result':{'capabilities':{}}})+'\\n')\n"
        "        sys.stdout.flush()\n"
        "    elif msg.get('method') == 'tools/list':\n"
        "        time.sleep(30)\n"
    )
    conn_hang = StdioMcpConnection("hang_srv", [sys.executable, "-c", hang_script], init_timeout_s=5.0)
    conn_hang.start()
    conn_hang.handshake()
    proc_ref = conn_hang.proc
    with pytest.raises(RequestTimeout):
        conn_hang.request("tools/list", timeout=0.15)
    assert conn_hang.alive is False
    if proc_ref is not None:
        assert proc_ref.poll() is not None
    conn_hang.stop()


def test_exponential_backoff_and_circuit_breaker_and_restart_reset():
    bad_cmd = [sys.executable, "-c", "import sys; sys.exit(2)"]
    svc = McpClientService(
        _make_cfg(
            enabled=True,
            base_backoff_s=0.08,
            max_backoff_s=0.4,
            circuit_threshold=2,
            servers=[{"name": "broken", "command": bad_cmd, "autostart": False}],
        )
    )
    try:
        with pytest.raises(TransportError):
            svc.tools("broken")
        st1 = _srv_status(svc, "broken")
        assert st1["failures"] == 1
        assert st1["circuit_open"] is False

        time.sleep(0.11)
        with pytest.raises(TransportError):
            svc.tools("broken")
        st2 = _srv_status(svc, "broken")
        assert st2["failures"] == 2
        assert st2["circuit_open"] is True
        assert st2["retry_after_s"] > 0.0

        t0 = time.monotonic()
        with pytest.raises(TransportError, match="circuit_open"):
            svc.tools("broken")
        assert (time.monotonic() - t0) < 0.08

        svc._server_specs["broken"]["command"] = _echo_cmd()
        res = svc.restart("broken")
        assert res["ok"] is True
        st3 = _srv_status(svc, "broken")
        assert st3["failures"] == 0
        assert st3["circuit_open"] is False
    finally:
        svc.stop()


def test_select_relevant_tools_scans_alive_only_and_caches_embeddings(monkeypatch):
    embed_calls = {"n": 0}

    class StubEmbedEngine:
        is_available = True

        @classmethod
        def get_instance(cls):
            return cls()

        @staticmethod
        def embed_vector(text):
            return [1.0, 0.0]

        @staticmethod
        def embed_passage(text):
            embed_calls["n"] += 1
            return [1.0 if "echo" in str(text).lower() else 0.1, 0.0]

    monkeypatch.setattr("modules.agent_core.services.system1_embed.System1EmbedEngine", StubEmbedEngine)

    svc = McpClientService(
        _make_cfg(
            enabled=True,
            servers=[
                {"name": "echo", "command": _echo_cmd(), "autostart": False},
                {"name": "unstarted", "command": _echo_cmd(), "autostart": False},
            ],
        )
    )
    try:
        res = svc.tools("echo")
        assert len(res["tools"]) >= 1
        assert "unstarted" not in svc._conns

        sel1 = svc.select_relevant_tools("echo message")
        assert len(sel1) >= 1
        assert "unstarted" not in svc._conns
        assert len(svc._tool_embed_cache) == len(res["tools"])
        first_calls = embed_calls["n"]
        assert first_calls == len(res["tools"])

        sel2 = svc.select_relevant_tools("echo message")
        assert sel1 == sel2
        assert embed_calls["n"] == first_calls
    finally:
        svc.stop()


def test_gateway_include_mcp_client_cleanup_hook_and_main_lifespan(monkeypatch):
    from modules.gateway.services.bootstrap_ai import _include_mcp_client
    from modules.gateway.xGatewayService import _shutdown_started_services
    import modules.mcp_client.__main__ as mc_main

    gw_app = FastAPI()
    started = {}
    _include_mcp_client(gw_app, started)
    assert "mcp_client" in started
    mcp_svc = started["mcp_client"]
    assert any(getattr(h, "__self__", None) is mcp_svc for h in started.get("_cleanup_hooks", []))

    stopped = {"called": False}

    class DummyConn:
        alive = True

        def stop(self):
            stopped["called"] = True

    mcp_svc._conns["dummy"] = DummyConn()  # type: ignore[assignment]
    asyncio.run(_shutdown_started_services(started))
    assert stopped["called"] is True
    assert "dummy" not in mcp_svc._conns

    captured = {}

    def fake_run(app, host=None, port=None, log_level=None):
        captured["app"] = app
        captured["host"] = host

    monkeypatch.setenv("MCP_CLIENT_HOST", "0.0.0.0")
    monkeypatch.setattr(mc_main.uvicorn, "run", fake_run)
    assert mc_main.main() == 0
    assert captured["host"] == "0.0.0.0"
    main_app = captured["app"]
    assert isinstance(main_app, FastAPI)
    with TestClient(main_app) as client:
        assert client.get("/mcp_client/healthz").status_code in (200, 404)
