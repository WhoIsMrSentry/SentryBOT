from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional

import requests

logger = logging.getLogger("mcp_server.xMcpServerService")


class xMcpServerService:
    """Exposes SentryBOT capabilities as MCP tools over JSON-RPC transports."""

    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        cfg = cfg if isinstance(cfg, dict) else {}
        server_cfg = cfg.get("mcp_server", {}) if isinstance(cfg.get("mcp_server"), dict) else {}
        self.enabled = bool(server_cfg.get("enabled", True))
        self.transport = str(server_cfg.get("transport", "stdio")).strip().lower()
        self.protocol_version = str(server_cfg.get("protocol_version", "2024-11-05"))
        self.server_name = str(server_cfg.get("server_name", "sentrybot"))
        self.server_version = str(server_cfg.get("server_version", "1.0.0"))
        self.gateway_base = str(server_cfg.get("gateway_base", "http://127.0.0.1:8080")).rstrip("/")
        self.request_timeout_s = float(server_cfg.get("request_timeout_s", 6.0))
        self.auth_token = str(server_cfg.get("auth_token", "") or "")
        self.tools_cfg: List[Dict[str, Any]] = [
            t for t in server_cfg.get("tools", []) or [] if isinstance(t, dict)
        ]
        self._tool_index: Dict[str, Dict[str, Any]] = {
            str(t.get("name", "")).strip(): t for t in self.tools_cfg if str(t.get("name", "")).strip()
        }

    def is_available(self) -> bool:
        return bool(self.enabled and self.tools_cfg)

    def list_tools(self) -> List[Dict[str, Any]]:
        tools = []
        for name, spec in self._tool_index.items():
            tools.append(
                {
                    "name": name,
                    "description": str(spec.get("description", "")),
                    "inputSchema": self._input_schema(spec),
                }
            )
        return tools

    @staticmethod
    def _input_schema(spec: Dict[str, Any]) -> Dict[str, Any]:
        args = spec.get("args") if isinstance(spec.get("args"), dict) else {}
        properties: Dict[str, Any] = {}
        required: List[str] = []
        for arg_name, arg_spec in args.items():
            arg_spec = arg_spec if isinstance(arg_spec, dict) else {}
            props: Dict[str, Any] = {"type": str(arg_spec.get("type", "string"))}
            if arg_spec.get("description"):
                props["description"] = str(arg_spec["description"])
            properties[str(arg_name)] = props
            if bool(arg_spec.get("required", False)):
                required.append(str(arg_name))
        return {"type": "object", "properties": properties, "required": required}

    def execute_tool(self, name: str, arguments: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
        if not self.is_available():
            return {"isError": True, "content": [{"type": "text", "text": "mcp_server_disabled"}]}
        spec = self._tool_index.get(str(name).strip())
        if spec is None:
            return {"isError": True, "content": [{"type": "text", "text": f"unknown_tool:{name}"}]}
        args = dict(arguments or {})
        path_spec = str(spec.get("path", ""))
        method = str(spec.get("method", "GET")).upper()
        try:
            path = self._resolve_path(path_spec, args)
            url = self.gateway_base + path
            timeout = self.request_timeout_s
            headers = {}
            if self.auth_token:
                headers["X-Auth-Token"] = self.auth_token
            if method in ("GET", "DELETE"):
                resp = requests.request(method, url, params=args, headers=headers, timeout=timeout)
            else:
                resp = requests.request(method, url, json=args, headers=headers, timeout=timeout)
            body: Any
            try:
                body = resp.json()
            except ValueError:
                body = {"text": resp.text[:800]}
            text = _summarize(body)
            return {"isError": resp.status_code >= 400, "content": [{"type": "text", "text": text}]}
        except Exception as exc:
            logger.debug("tool %s failed: %s", name, exc)
            return {"isError": True, "content": [{"type": "text", "text": f"tool_error:{exc}"}]}

    @staticmethod
    def _resolve_path(path_spec: str, args: Dict[str, Any]) -> str:
        path = path_spec
        for key, value in list(args.items()):
            token = "{" + key + "}"
            if token in path:
                path = path.replace(token, str(value))
                args.pop(key)
        return path

    def status(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "available": self.is_available(),
            "transport": self.transport,
            "server_name": self.server_name,
            "protocol_version": self.protocol_version,
            "gateway_base": self.gateway_base,
            "tools": list(self._tool_index.keys()),
        }


def _summarize(body: Any) -> str:
    try:
        import json

        text = json.dumps(body, ensure_ascii=False)
    except Exception:
        text = str(body)
    return text[:2000]
