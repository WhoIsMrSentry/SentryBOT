"""Demo external MCP server (stdlib only): echo + add tools for tests/examples."""
from __future__ import annotations

import json
import sys


def list_tools():
    return [
        {
            "name": "echo",
            "description": "Verilen metni geri dondurur.",
            "inputSchema": {
                "type": "object",
                "properties": {"text": {"type": "string", "description": "Yankilanan metin"}},
                "required": ["text"],
            },
        },
        {
            "name": "add",
            "description": "Iki sayiyi toplar.",
            "inputSchema": {
                "type": "object",
                "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                "required": ["a", "b"],
            },
        },
    ]


def call_tool(name, args):
    args = args or {}
    if name == "echo":
        return {"content": [{"type": "text", "text": f"echo:{args.get('text', '')}"}], "isError": False}
    if name == "add":
        try:
            total = float(args.get("a", 0)) + float(args.get("b", 0))
            text = str(int(total)) if float(total).is_integer() else str(total)
        except Exception as exc:
            return {"content": [{"type": "text", "text": f"tool_error:{exc}"}], "isError": True}
        return {"content": [{"type": "text", "text": text}], "isError": False}
    return {"content": [{"type": "text", "text": f"unknown_tool:{name}"}], "isError": True}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if not isinstance(msg, dict):
            continue
        method = msg.get("method", "")
        mid = msg.get("id")
        if method == "initialize":
            out = {
                "jsonrpc": "2.0",
                "id": mid,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "echo-demo", "version": "0.1.0"},
                },
            }
        elif method == "tools/list":
            out = {"jsonrpc": "2.0", "id": mid, "result": {"tools": list_tools()}}
        elif method == "tools/call":
            res = call_tool((msg.get("params") or {}).get("name", ""), (msg.get("params") or {}).get("arguments"))
            out = {"jsonrpc": "2.0", "id": mid, "result": res}
        elif method == "ping":
            out = {"jsonrpc": "2.0", "id": mid, "result": {}}
        elif mid is None:
            continue  # notification
        elif method == "notifications/initialized":
            continue
        else:
            out = {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method_not_found:{method}"}}
        if mid is None:
            continue
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
