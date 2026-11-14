from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

import requests

logger = logging.getLogger("mcp_server.xMcpServerService")

_SAFE_PATH_PARAM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

_DEFAULT_RESOURCES: List[Dict[str, Any]] = [
    {
        "uri": "sentrybot://autonomy/state",
        "name": "Autonomy State",
        "description": "Robotun anlik otonomi modu, hedefi ve sistem ozeti.",
        "mimeType": "application/json",
        "path": "/autonomy/state",
    },
    {
        "uri": "sentrybot://persona/active",
        "name": "Active Persona",
        "description": "Aktif konusma/kisilik adi ve sistem istemi ozeti.",
        "mimeType": "application/json",
        "path": "/ollama/persona",
    },
]


class xMcpServerService:
    """Exposes SentryBOT capabilities as MCP tools and read-only resources."""

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
        self.read_only = bool(server_cfg.get("read_only", False))
        self.allowed_tools = {
            str(item).strip() for item in (server_cfg.get("allowed_tools") or []) if str(item).strip()
        }
        self._session = requests.Session()
        self.tools_cfg: List[Dict[str, Any]] = [
            t for t in server_cfg.get("tools", []) or [] if isinstance(t, dict)
        ]
        self._tool_index: Dict[str, Dict[str, Any]] = {
            str(t.get("name", "")).strip(): t for t in self.tools_cfg if str(t.get("name", "")).strip()
        }
        self._resource_index: Dict[str, Dict[str, Any]] = {r["uri"]: r for r in _DEFAULT_RESOURCES}

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass

    def _http_request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        req_fn = getattr(requests, "request", None)
        if getattr(req_fn, "__module__", "") == "requests.api":
            return self._session.request(method, url, **kwargs)
        return requests.request(method, url, **kwargs)

    def is_available(self) -> bool:
        return bool(self.enabled and self.tools_cfg)

    def _is_tool_permitted(self, name: str, spec: Dict[str, Any]) -> bool:
        if self.allowed_tools and name not in self.allowed_tools:
            return False
        if self.read_only and not self._spec_is_read_only(spec):
            return False
        return True

    @staticmethod
    def _spec_is_read_only(spec: Dict[str, Any]) -> bool:
        if "read_only" in spec:
            return bool(spec.get("read_only"))
        return str(spec.get("method", "GET")).upper() in ("GET", "HEAD", "OPTIONS")

    def list_tools(self) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []
        tools = []
        for name, spec in self._tool_index.items():
            if not self._is_tool_permitted(name, spec):
                continue
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
            if isinstance(arg_spec.get("enum"), list) and arg_spec["enum"]:
                props["enum"] = list(arg_spec["enum"])
            properties[str(arg_name)] = props
            if bool(arg_spec.get("required", False)):
                required.append(str(arg_name))
        return {"type": "object", "properties": properties, "required": required}

    @staticmethod
    def _validate_args(spec: Dict[str, Any], args: Dict[str, Any]) -> None:
        schema_args = spec.get("args") if isinstance(spec.get("args"), dict) else {}
        for arg_name, raw_spec in schema_args.items():
            arg_spec = raw_spec if isinstance(raw_spec, dict) else {}
            present = arg_name in args and args[arg_name] is not None
            if bool(arg_spec.get("required", False)) and not present:
                raise ValueError(f"missing required argument '{arg_name}'")
            if not present:
                continue
            val = args[arg_name]
            expected = str(arg_spec.get("type", "string")).strip().lower()
            if expected == "string" and not isinstance(val, str):
                raise ValueError(f"argument '{arg_name}' must be string")
            elif expected == "integer" and (isinstance(val, bool) or not isinstance(val, int)):
                raise ValueError(f"argument '{arg_name}' must be integer")
            elif expected == "number" and (isinstance(val, bool) or not isinstance(val, (int, float))):
                raise ValueError(f"argument '{arg_name}' must be number")
            elif expected == "boolean" and not isinstance(val, bool):
                raise ValueError(f"argument '{arg_name}' must be boolean")
            elif expected == "object" and not isinstance(val, dict):
                raise ValueError(f"argument '{arg_name}' must be object")
            elif expected == "array" and not isinstance(val, list):
                raise ValueError(f"argument '{arg_name}' must be array")

            allowed_enum = arg_spec.get("enum")
            if isinstance(allowed_enum, list) and allowed_enum and val not in allowed_enum:
                raise ValueError(f"argument '{arg_name}' must be one of {allowed_enum}")

    def execute_tool(self, name: str, arguments: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
        if not self.is_available():
            return {"isError": True, "content": [{"type": "text", "text": "mcp_server_disabled"}]}
        tool_name = str(name).strip()
        spec = self._tool_index.get(tool_name)
        if spec is None:
            return {"isError": True, "content": [{"type": "text", "text": f"unknown_tool:{name}"}]}
        if not self._is_tool_permitted(tool_name, spec):
            return {"isError": True, "content": [{"type": "text", "text": f"tool_forbidden:{tool_name}"}]}

        args = dict(arguments or {})
        try:
            self._validate_args(spec, args)
            path_spec = str(spec.get("path", ""))
            method = str(spec.get("method", "GET")).upper()
            path = self._resolve_path(path_spec, args)
        except ValueError as exc:
            return {"isError": True, "content": [{"type": "text", "text": f"invalid_argument:{exc}"}]}

        url = self.gateway_base + path
        timeout = self.request_timeout_s
        headers = {}
        if self.auth_token:
            headers["X-Auth-Token"] = self.auth_token

        param_in = str(spec.get("param_in", "")).strip().lower()
        if not param_in:
            param_in = "query" if method in ("GET", "DELETE") else "json"

        try:
            if param_in == "query":
                resp = self._http_request(method, url, params=args, headers=headers, timeout=timeout)
            elif param_in == "body":
                raw_body = args["payload"] if ("payload" in args and isinstance(args["payload"], dict)) else args
                resp = self._http_request(method, url, json=raw_body, headers=headers, timeout=timeout)
            else:
                resp = self._http_request(method, url, json=args, headers=headers, timeout=timeout)

            body: Any
            try:
                body = resp.json()
            except ValueError:
                body = {"text": str(getattr(resp, "text", ""))[:800]}

            text = _summarize(body)
            result: Dict[str, Any] = {
                "isError": int(getattr(resp, "status_code", 200)) >= 400,
                "content": [{"type": "text", "text": text}],
            }
            if isinstance(body, dict):
                result["structuredContent"] = body
            return result
        except Exception as exc:
            logger.debug("tool %s failed: %s", tool_name, exc)
            return {"isError": True, "content": [{"type": "text", "text": f"tool_error:{exc}"}]}

    def list_resources(self) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []
        return [
            {
                "uri": res["uri"],
                "name": res["name"],
                "description": res["description"],
                "mimeType": res["mimeType"],
            }
            for res in _DEFAULT_RESOURCES
        ]

    def read_resource(self, uri: str) -> Dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "mcp_server_disabled", "contents": []}
        spec = self._resource_index.get(str(uri or "").strip())
        if spec is None:
            raise KeyError(f"unknown_resource:{uri}")
        headers = {"X-Auth-Token": self.auth_token} if self.auth_token else {}
        resp = self._http_request("GET", self.gateway_base + spec["path"], headers=headers, timeout=self.request_timeout_s)
        if int(getattr(resp, "status_code", 200)) >= 400:
            raise RuntimeError(f"http_{resp.status_code}")
        try:
            payload = resp.json()
            text = json.dumps(payload, ensure_ascii=False)
        except ValueError:
            text = str(getattr(resp, "text", ""))
        return {
            "contents": [
                {
                    "uri": spec["uri"],
                    "mimeType": spec["mimeType"],
                    "text": text,
                }
            ]
        }

    @staticmethod
    def resolve_path_pure(
        path_spec: str,
        args: Optional[Mapping[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """Resolve {key} placeholders safely without allowing path traversal."""
        path = str(path_spec or "")
        remaining: Dict[str, Any] = dict(args or {})
        for key, value in list(remaining.items()):
            token = "{" + str(key) + "}"
            if token in path:
                val_str = str(value).strip()
                if ".." in val_str or "/" in val_str or "\\" in val_str or not _SAFE_PATH_PARAM_RE.match(val_str):
                    raise ValueError(f"unsafe path parameter '{key}': {value!r}")
                path = path.replace(token, val_str)
                remaining.pop(key, None)
        return path, remaining

    @staticmethod
    def _resolve_path(path_spec: str, args: Dict[str, Any]) -> str:
        path, remaining = xMcpServerService.resolve_path_pure(path_spec, args)
        if isinstance(args, dict):
            for key in list(args.keys()):
                if key not in remaining:
                    args.pop(key, None)
        return path

    def status(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "available": self.is_available(),
            "enabled": self.enabled,
            "read_only": self.read_only,
            "allowed_tools": sorted(self.allowed_tools),
            "transport": self.transport,
            "server_name": self.server_name,
            "protocol_version": self.protocol_version,
            "gateway_base": self.gateway_base,
            "tools": [t["name"] for t in self.list_tools()],
            "resources": [r["uri"] for r in self.list_resources()],
        }


def _summarize(body: Any, max_chars: int = 2000) -> str:
    try:
        text = json.dumps(body, ensure_ascii=False)
    except Exception:
        text = str(body)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."
