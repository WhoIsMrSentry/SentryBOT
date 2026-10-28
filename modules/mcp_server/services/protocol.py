from __future__ import annotations

import logging
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger("mcp_server.protocol")

JSONRPC_VERSION = "2.0"


class McpProtocol:
    """Minimal MCP server protocol (2024-11-05): initialize, tools/list, tools/call."""

    def __init__(self, service: Any) -> None:
        self.service = service
        self._initialized = False

    def handle(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        method = str(msg.get("method", ""))
        msg_id = msg.get("id")
        try:
            if method == "initialize":
                params = msg.get("params") or {}
                self._initialized = True
                return {
                    "jsonrpc": JSONRPC_VERSION,
                    "id": msg_id,
                    "result": {
                        "protocolVersion": self.service.protocol_version,
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": self.service.server_name,
                            "version": self.service.server_version,
                        },
                    },
                }

            if method == "notifications/initialized":
                return None

            if method == "ping":
                return {"jsonrpc": JSONRPC_VERSION, "id": msg_id, "result": {}}

            if method == "tools/list":
                return {"jsonrpc": JSONRPC_VERSION, "id": msg_id, "result": {"tools": self.service.list_tools()}}

            if method == "tools/call":
                params = msg.get("params") or {}
                name = str(params.get("name", ""))
                arguments = params.get("arguments") or {}
                result = self.service.execute_tool(name, arguments)
                structured = result.get("content") if isinstance(result, dict) else None
                texts = []
                for item in structured or []:
                    if isinstance(item, dict) and item.get("text"):
                        texts.append(str(item["text"]))
                payload = "\n".join(texts) if texts else "ok"
                return {
                    "jsonrpc": JSONRPC_VERSION,
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": payload}],
                        "isError": bool(result.get("isError", False)) if isinstance(result, dict) else False,
                    },
                }

            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": msg_id,
                "error": {"code": -32601, "message": f"method_not_found:{method}"},
            }
        except Exception as exc:
            logger.debug("protocol error handling %s: %s", method, exc)
            if msg_id is None:
                return None
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": msg_id,
                "error": {"code": -32603, "message": f"internal_error:{exc}"},
            }


def run_stdio(protocol: McpProtocol, reader=None, writer=None) -> int:
    import json

    reader = reader or sys.stdin
    writer = writer or sys.stdout
    count = 0
    for line in reader:
        line = line.strip()
        if not line:
            continue
        count += 1
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if not isinstance(msg, dict):
            continue
        if count == 1 and msg.get("method") == "initialize":
            logger.info("mcp stdio session started")
        response = protocol.handle(msg)
        if response is not None:
            try:
                writer.write(json.dumps(response, ensure_ascii=False) + "\n")
                writer.flush()
            except Exception:
                break
    return 0
