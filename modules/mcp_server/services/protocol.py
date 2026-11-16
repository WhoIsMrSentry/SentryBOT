from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger("mcp_server.protocol")

JSONRPC_VERSION = "2.0"


class McpProtocol:
    """MCP server JSON-RPC protocol (2024-11-05): initialize, tools/*, resources/*."""

    def __init__(self, service: Any) -> None:
        self.service = service
        self._initialized = False

    def _not_initialized_error(self, msg_id: Any) -> Dict[str, Any]:
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": msg_id,
            "error": {"code": -32002, "message": "server_not_initialized"},
        }

    def handle(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        method = str(msg.get("method", ""))
        msg_id = msg.get("id")
        try:
            if method == "initialize":
                self._initialized = True
                return {
                    "jsonrpc": JSONRPC_VERSION,
                    "id": msg_id,
                    "result": {
                        "protocolVersion": self.service.protocol_version,
                        "capabilities": {"tools": {}, "resources": {}},
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

            if not self._initialized:
                if msg_id is None:
                    return None
                return self._not_initialized_error(msg_id)

            if method == "tools/list":
                tools = self.service.list_tools() if getattr(self.service, "enabled", True) else []
                return {"jsonrpc": JSONRPC_VERSION, "id": msg_id, "result": {"tools": tools}}

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
                payload_text = "\n".join(texts) if texts else "ok"
                rpc_result: Dict[str, Any] = {
                    "content": [{"type": "text", "text": payload_text}],
                    "isError": bool(result.get("isError", False)) if isinstance(result, dict) else False,
                }
                if isinstance(result, dict) and isinstance(result.get("structuredContent"), dict):
                    rpc_result["structuredContent"] = result["structuredContent"]
                return {"jsonrpc": JSONRPC_VERSION, "id": msg_id, "result": rpc_result}

            if method == "resources/list":
                resources = (
                    self.service.list_resources()
                    if hasattr(self.service, "list_resources") and getattr(self.service, "enabled", True)
                    else []
                )
                return {"jsonrpc": JSONRPC_VERSION, "id": msg_id, "result": {"resources": resources}}

            if method == "resources/read":
                params = msg.get("params") or {}
                uri = str(params.get("uri", ""))
                if not hasattr(self.service, "read_resource"):
                    return {
                        "jsonrpc": JSONRPC_VERSION,
                        "id": msg_id,
                        "error": {"code": -32601, "message": "resources_not_supported"},
                    }
                try:
                    data = self.service.read_resource(uri)
                except KeyError as exc:
                    return {
                        "jsonrpc": JSONRPC_VERSION,
                        "id": msg_id,
                        "error": {"code": -32602, "message": str(exc)},
                    }
                return {"jsonrpc": JSONRPC_VERSION, "id": msg_id, "result": data}

            if msg_id is None:
                return None
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
        except Exception as exc:
            err_resp = {
                "jsonrpc": JSONRPC_VERSION,
                "id": None,
                "error": {"code": -32700, "message": f"parse_error:{exc}"},
            }
            try:
                writer.write(json.dumps(err_resp, ensure_ascii=False) + "\n")
                writer.flush()
            except Exception:
                break
            continue
        if not isinstance(msg, dict):
            err_resp = {
                "jsonrpc": JSONRPC_VERSION,
                "id": None,
                "error": {"code": -32600, "message": "invalid_request:expected_object"},
            }
            try:
                writer.write(json.dumps(err_resp, ensure_ascii=False) + "\n")
                writer.flush()
            except Exception:
                break
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
