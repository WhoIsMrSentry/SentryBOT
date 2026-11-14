import io
import json

from modules.mcp_server.config_loader import load_config
from modules.mcp_server.services.protocol import McpProtocol, run_stdio
from modules.mcp_server.xMcpServerService import xMcpServerService

CFG = load_config()


def make_service():
    return xMcpServerService(CFG)


def test_config_has_tools():
    service = make_service()
    assert service.is_available()
    names = [t["name"] for t in service.list_tools()]
    assert {"speak", "set_lights", "robot_state"} <= set(names)


def test_input_schema_required():
    service = make_service()
    schema = service._input_schema(service._tool_index["set_lights"])
    assert set(schema["required"]) == {"r_", "g", "b"}
    assert schema["properties"]["segment"]["type"] == "string"


def test_protocol_initialize_tools_list_tools_call(monkeypatch):
    service = make_service()
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["params"] = kwargs.get("params")
        captured["json"] = kwargs.get("json")

        class Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"ok": True, "echo": kwargs}

        return Resp()

    monkeypatch.setattr("modules.mcp_server.xMcpServerService.requests.request", fake_request)

    protocol = McpProtocol(service)
    init = protocol.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "sentrybot"
    assert init["result"]["protocolVersion"] == "2024-11-05"

    tools = protocol.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert any(t["name"] == "robot_state" for t in tools["result"]["tools"])

    call = protocol.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "set_lights",
                "arguments": {"r_": 255, "g": 10, "b": 30, "segment": "tail"},
            },
        }
    )
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/neopixel/fill")
    assert captured["params"]["r_"] == 255
    assert captured["params"]["g"] == 10
    assert captured["params"]["b"] == 30
    assert captured["params"]["segment"] == "tail"
    assert call["result"]["content"][0]["type"] == "text"
    assert '{"ok": true' in call["result"]["content"][0]["text"].lower()

    unknown = protocol.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nope"}})
    assert unknown["result"]["isError"] is True
    assert "unknown_tool" in unknown["result"]["content"][0]["text"]

    missing_method = protocol.handle({"jsonrpc": "2.0", "id": 5, "method": "bogus/method"})
    assert missing_method["error"]["code"] == -32601


def test_path_param_resolution():
    service = make_service()
    args = {"effect": "rainbow", "cycles": 2}
    path = service._resolve_path("/neopixel/{effect}", args)
    assert path == "/neopixel/rainbow"
    assert args == {"cycles": 2}


def test_stdio_loop_end_to_end():
    service = make_service()
    protocol = McpProtocol(service)
    messages = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
    ]
    inp = io.StringIO("\n".join(messages) + "\n")
    out = io.StringIO()
    run_stdio(protocol, reader=inp, writer=out)
    lines = [json.loads(x) for x in out.getvalue().strip().splitlines()]
    assert lines[0]["result"]["serverInfo"]["name"] == "sentrybot"
    assert len(lines[1]["result"]["tools"]) >= 5


def _init_protocol(protocol):
    init_res = protocol.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init_res is not None
    assert "error" not in init_res
    protocol.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    return init_res


def test_config_loader_and_live_router_contracts(monkeypatch):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from modules.mcp_server.config_loader import load_config
    from modules.visual_output.neopixel.api.router import get_router as neopixel_router
    from modules.arduino_serial.api.router import get_router as arduino_router
    from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService

    cfg = load_config()
    assert cfg["mcp_server"]["gateway_base"].startswith("http://")
    assert "@gateway" not in cfg["mcp_server"]["gateway_base"]
    assert cfg["mcp_server"].get("read_only") is False

    neo_calls = []

    class StubNeoRunner:
        driver = SimpleNamespace(num_leds=16)

        def list_segments(self):
            return [{"name": "tail", "start": 0, "count": 4}]

        def fill(self, r_, g, b):
            neo_calls.append(("fill", r_, g, b))

        def fill_segment(self, segment, r_, g, b):
            neo_calls.append(("fill_segment", segment, r_, g, b))

        def rainbow(self, wait=0.02, cycles=1):
            neo_calls.append(("rainbow", wait, cycles))

        def theater_chase(self, r_=255, g=255, b=255, wait=0.05, cycles=5):
            neo_calls.append(("theater_chase", r_, g, b, wait, cycles))

        def clear(self):
            neo_calls.append(("clear",))

    ard_sent = []
    ard_svc = xArduinoSerialService(config_overrides={"auto_heartbeat": False, "watchdog": {"enabled": False}})
    ard_svc.send = lambda obj: (ard_sent.append(obj) or {"ok": True, "echo": obj})  # type: ignore[method-assign]

    hw_app = FastAPI()
    hw_app.include_router(neopixel_router(StubNeoRunner()))
    hw_app.include_router(arduino_router(ard_svc))
    hw_client = TestClient(hw_app)

    svc = make_service()
    svc.gateway_base = "http://testserver"

    def _bridge_request(method, url, params=None, json=None, timeout=None, **_kwargs):
        path = url.replace("http://testserver", "")
        resp = hw_client.request(method, path, params=params, json=json)
        return SimpleNamespace(
            status_code=resp.status_code,
            text=resp.text,
            headers=dict(resp.headers),
            json=resp.json,
        )

    monkeypatch.setattr("modules.mcp_server.xMcpServerService.requests.request", _bridge_request)
    try:
        protocol = McpProtocol(svc)
        _init_protocol(protocol)

        res_fill = protocol.handle(
            {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": "set_lights",
                    "arguments": {"r_": 12, "g": 34, "b": 56, "segment": "tail"},
                },
            }
        )
        assert res_fill["result"]["isError"] is False
        assert isinstance(res_fill["result"].get("structuredContent"), dict)
        assert ("fill_segment", "tail", 12, 34, 56) in neo_calls

        res_fx = protocol.handle(
            {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {
                    "name": "lights_effect",
                    "arguments": {"effect": "rainbow", "wait": 0.01, "cycles": 1},
                },
            }
        )
        assert res_fx["result"]["isError"] is False
        assert ("rainbow", 0.01, 1) in neo_calls

        res_ard = protocol.handle(
            {
                "jsonrpc": "2.0",
                "id": 12,
                "method": "tools/call",
                "params": {
                    "name": "arduino_send",
                    "arguments": {"payload": {"cmd": "home"}},
                },
            }
        )
        assert res_ard["result"]["isError"] is False
        assert ard_sent == [{"cmd": "home"}]

        res_ard_bad = protocol.handle(
            {
                "jsonrpc": "2.0",
                "id": 13,
                "method": "tools/call",
                "params": {
                    "name": "arduino_send",
                    "arguments": {"payload": {"cmd": "invalid_unknown_cmd"}},
                },
            }
        )
        assert res_ard_bad["result"]["isError"] is True
    finally:
        svc.close()
        ard_svc.stop()


def test_validation_http_errors_traversal_and_disabled(monkeypatch):
    from types import SimpleNamespace
    import pytest

    for bad in ("../secret", "..\\secret", "/etc/passwd", "a/b", "a\\b", "", "."):
        with pytest.raises(ValueError):
            xMcpServerService.resolve_path_pure("/items/{item_id}/state", {"item_id": bad})
    resolved, rem = xMcpServerService.resolve_path_pure("/items/{item_id}/state", {"item_id": "sensor_1", "flag": True})
    assert resolved == "/items/sensor_1/state"
    assert rem == {"flag": True}

    svc = make_service()
    try:
        protocol = McpProtocol(svc)
        _init_protocol(protocol)

        # Missing required parameter & bool-as-int rejection
        bad_missing = protocol.handle(
            {
                "jsonrpc": "2.0",
                "id": 20,
                "method": "tools/call",
                "params": {"name": "set_lights", "arguments": {"g": 10, "b": 20}},
            }
        )
        assert bad_missing["result"]["isError"] is True

        bad_bool = protocol.handle(
            {
                "jsonrpc": "2.0",
                "id": 21,
                "method": "tools/call",
                "params": {"name": "set_lights", "arguments": {"r_": True, "g": 10, "b": 20}},
            }
        )
        assert bad_bool["result"]["isError"] is True

        # HTTP >= 400 reported as isError=True
        monkeypatch.setattr(
            "modules.mcp_server.xMcpServerService.requests.request",
            lambda *_a, **_k: SimpleNamespace(
                status_code=503,
                text='{"detail":"unavailable"}',
                headers={"content-type": "application/json"},
                json=lambda: {"detail": "unavailable"},
            ),
        )
        err_res = protocol.handle(
            {
                "jsonrpc": "2.0",
                "id": 22,
                "method": "tools/call",
                "params": {"name": "set_lights", "arguments": {"r_": 1, "g": 2, "b": 3}},
            }
        )
        assert err_res["result"]["isError"] is True

        # enabled=False hides tools/resources and blocks tool execution
        svc.enabled = False
        listed = protocol.handle({"jsonrpc": "2.0", "id": 23, "method": "tools/list"})
        assert listed["result"]["tools"] == []
        res_listed = protocol.handle({"jsonrpc": "2.0", "id": 24, "method": "resources/list"})
        assert res_listed["result"]["resources"] == []
        blocked = protocol.handle(
            {
                "jsonrpc": "2.0",
                "id": 25,
                "method": "tools/call",
                "params": {"name": "set_lights", "arguments": {"r_": 1, "g": 2, "b": 3}},
            }
        )
        assert blocked["result"]["isError"] is True
    finally:
        svc.close()


def test_protocol_init_guard_and_parse_errors():
    svc = make_service()
    try:
        protocol = McpProtocol(svc)
        uninit_tools = protocol.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert uninit_tools["error"]["code"] == -32002
        uninit_res = protocol.handle({"jsonrpc": "2.0", "id": 2, "method": "resources/list"})
        assert uninit_res["error"]["code"] == -32002

        inp = io.StringIO("{not valid json\n[1, 2, 3]\n")
        out = io.StringIO()
        run_stdio(protocol, reader=inp, writer=out)
        replies = [json.loads(line) for line in out.getvalue().strip().splitlines()]
        assert len(replies) == 2
        assert replies[0]["error"]["code"] == -32700
        assert replies[1]["error"]["code"] == -32600
    finally:
        svc.close()


def test_read_only_allowed_tools_and_resources(monkeypatch):
    from types import SimpleNamespace

    svc = make_service()
    try:
        protocol = McpProtocol(svc)
        init_res = _init_protocol(protocol)
        caps = init_res["result"]["capabilities"]
        assert "tools" in caps and "resources" in caps

        svc.read_only = True
        ro_tools = {t["name"] for t in protocol.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]}
        assert "set_lights" not in ro_tools
        assert "arduino_send" not in ro_tools

        denied = protocol.handle(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "set_lights", "arguments": {"r_": 1, "g": 2, "b": 3}},
            }
        )
        assert denied["result"]["isError"] is True

        svc.read_only = False
        svc.allowed_tools = {"set_lights"}
        allow_tools = {t["name"] for t in protocol.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})["result"]["tools"]}
        assert allow_tools == {"set_lights"}
        denied_other = protocol.handle(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "arduino_send", "arguments": {"payload": {"cmd": "home"}}},
            }
        )
        assert denied_other["result"]["isError"] is True

        svc.allowed_tools = set()
        res_list = protocol.handle({"jsonrpc": "2.0", "id": 5, "method": "resources/list"})["result"]["resources"]
        uris = {r["uri"] for r in res_list}
        assert "sentrybot://autonomy/state" in uris
        assert "sentrybot://persona/active" in uris

        monkeypatch.setattr(
            "modules.mcp_server.xMcpServerService.requests.request",
            lambda method, url, **_k: SimpleNamespace(
                status_code=200,
                text='{"mode":"idle"}',
                headers={"content-type": "application/json"},
                json=lambda: {"mode": "idle", "url": url, "method": method},
            ),
        )
        read_ok = protocol.handle(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "resources/read",
                "params": {"uri": "sentrybot://autonomy/state"},
            }
        )
        assert "contents" in read_ok["result"]
        assert read_ok["result"]["contents"][0]["uri"] == "sentrybot://autonomy/state"

        read_missing = protocol.handle(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "resources/read",
                "params": {"uri": "sentrybot://does/not/exist"},
            }
        )
        assert "error" in read_missing
    finally:
        svc.close()


def test_mcp_server_http_router_and_gateway_mount():
    import asyncio
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from modules.mcp_server.api.router import get_router
    from modules.gateway.services.bootstrap_ai import _include_mcp_server
    from modules.gateway.xGatewayService import _shutdown_started_services

    svc = make_service()
    try:
        app = FastAPI()
        app.include_router(get_router(svc))
        client = TestClient(app)

        assert client.get("/mcp/healthz").status_code == 200
        assert client.get("/mcp/status").status_code == 200
        assert isinstance(client.get("/mcp/tools").json().get("tools"), list)
        res_r = client.get("/mcp/resources")
        assert res_r.status_code == 200
        assert any(r["uri"] == "sentrybot://autonomy/state" for r in res_r.json().get("resources", []))
    finally:
        svc.close()

    gw_app = FastAPI()
    started = {}
    _include_mcp_server(gw_app, started)
    assert "mcp_server" in started
    assert any(getattr(h, "__self__", None) is started["mcp_server"] for h in started.get("_cleanup_hooks", []))
    gw_client = TestClient(gw_app)
    assert gw_client.get("/mcp/healthz").status_code == 200
    assert gw_client.get("/mcp/resources").status_code == 200
    asyncio.run(_shutdown_started_services(started))


def test_mcp_server_main_stdio_routes_logs_to_stderr():
    import subprocess
    import sys

    init_line = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    proc = subprocess.run(
        [sys.executable, "-m", "modules.mcp_server"],
        input=init_line + "\n",
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert proc.returncode == 0
    stdout_lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert len(stdout_lines) >= 1
    parsed = json.loads(stdout_lines[0])
    assert parsed["id"] == 1
    assert parsed["result"]["serverInfo"]["name"] == "sentrybot"
