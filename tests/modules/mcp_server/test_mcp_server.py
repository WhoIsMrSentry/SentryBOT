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
    assert set(schema["required"]) == {"r", "g", "b"}
    assert schema["properties"]["segment"]["type"] == "string"


def test_protocol_initialize_tools_list_tools_call(monkeypatch):
    service = make_service()
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
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
                "arguments": {"r": 255, "g": 10, "b": 30, "segment": "tail"},
            },
        }
    )
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/neopixel/fill")
    assert captured["json"]["r"] == 255
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
