"""MCP client service: consumes external MCP servers (stdio) from SentryBOT."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional

from modules.mcp_client.services.stdio_process import (
    McpClientError,
    RemoteError,
    RequestTimeout,
    ServerNotFound,
    StdioMcpConnection,
    TransportError,
)

logger = logging.getLogger("mcp_client.service")


class McpClientService:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        cfg = cfg if isinstance(cfg, dict) else {}
        c = cfg.get("mcp_client", {}) if isinstance(cfg.get("mcp_client"), dict) else {}
        self.enabled = bool(c.get("enabled", True))
        client_cfg = c.get("client", {}) if isinstance(c.get("client"), dict) else {}
        self.client_name = str(client_cfg.get("name", "sentrybot-mcp-client"))
        self.client_version = str(client_cfg.get("version", "0.1.0"))
        self.protocol_version = str(client_cfg.get("protocol_version", "2024-11-05"))
        self.init_timeout_s = float(client_cfg.get("init_timeout_s", 15.0))
        self.request_timeout_s = float(client_cfg.get("request_timeout_s", 20.0))
        self._server_specs: Dict[str, Dict[str, Any]] = {}
        for spec in c.get("servers", []) or []:
            if isinstance(spec, dict) and str(spec.get("name", "")).strip():
                self._server_specs[str(spec["name"]).strip()] = spec
        self._conns: Dict[str, StdioMcpConnection] = {}

    # ---- management -----------------------------------------------------

    def _spec(self, name: str) -> Dict[str, Any]:
        spec = self._server_specs.get(str(name).strip())
        if not spec:
            raise ServerNotFound(f"unknown_server:{name} known={list(self._server_specs)}")
        return spec

    def _connection_for(self, name: str) -> StdioMcpConnection:
        name = str(name).strip()
        spec = self._spec(name)
        if not bool(spec.get("enabled", True)):
            raise TransportError(f"disabled:{name}")
        conn = self._conns.get(name)
        if conn is not None and conn.alive:
            return conn
        if conn is not None:
            self._conns.pop(name, None)
        conn = StdioMcpConnection(
            name=name,
            command=list(spec.get("command") or []),
            args=list(spec.get("args") or []),
            cwd=spec.get("cwd") or None,
            env=spec.get("env") or None,
            protocol_version=self.protocol_version,
            client_name=self.client_name,
            client_version=self.client_version,
            init_timeout_s=float(spec.get("init_timeout_s", self.init_timeout_s)),
            request_timeout_s=float(spec.get("request_timeout_s", self.request_timeout_s)),
        )
        conn.start()
        conn.handshake()
        self._conns[name] = conn
        return conn

    def connect_all_autostart(self) -> Dict[str, Any]:
        started, failed = [], []
        for name, spec in self._server_specs.items():
            if not bool(spec.get("enabled", True)) or not bool(spec.get("autostart", False)):
                continue
            try:
                self._connection_for(name)
                started.append(name)
            except McpClientError as exc:
                failed.append({"server": name, "error": str(exc)})
        return {"started": started, "failed": failed}

    def stop(self, name: Optional[str] = None) -> Dict[str, Any]:
        names = [str(name)] if name else list(self._conns)
        stopped = []
        for n in names:
            conn = self._conns.pop(n, None)
            if conn is not None:
                conn.stop()
                stopped.append(n)
        return {"stopped": stopped}

    def restart(self, name: str) -> Dict[str, Any]:
        self.stop(name)
        info = self._connection_for(name).server_info
        return {"ok": True, "server": name, "server_info": info}

    # ---- tools ----------------------------------------------------------

    def tools(self, name: Optional[str] = None, refresh: bool = False) -> Dict[str, Any]:
        if name:
            conn = self._connection_for(name)
            return {"ok": True, "server": name, "tools": conn.tools(refresh=refresh)}
        agg: Dict[str, List[Dict[str, Any]]] = {}
        errors = []
        for server in self._server_specs:
            try:
                agg[server] = self._connection_for(server).tools(refresh=refresh)
            except McpClientError as exc:
                errors.append({"server": server, "error": str(exc)})
        return {"ok": True, "servers": agg, "errors": errors}

    def call(self, server: str, tool: str, arguments: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        conn = self._connection_for(server)
        res = conn.call(tool, arguments)
        is_error = bool(res.get("isError", False))
        texts = []
        for item in res.get("content") or []:
            if isinstance(item, dict) and item.get("text"):
                texts.append(str(item["text"]))
        out: Dict[str, Any] = {
            "ok": True,
            "server": server,
            "tool": tool,
            "is_error": is_error,
            "text": "\n".join(texts) if texts else "ok",
        }
        if isinstance(res.get("structuredContent"), dict):
            out["data"] = res["structuredContent"]
        return out

    # ---- telemetry ------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        servers = []
        for name, spec in self._server_specs.items():
            conn = self._conns.get(name)
            state: Dict[str, Any] = {
                "name": name,
                "enabled": bool(spec.get("enabled", True)),
                "autostart": bool(spec.get("autostart", False)),
                "connected": bool(conn is not None and conn.alive),
                "server_info": dict(conn.server_info) if conn else {},
                "tools_cached": len(conn.tools_cache) if conn else 0,
                "last_error": conn.last_error if conn else "",
            }
            servers.append(state)
        return {"ok": self.enabled, "enabled": self.enabled, "servers": servers}

    def health(self) -> bool:
        if not self.enabled:
            return False
        return True
