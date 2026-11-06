"""MCP client service: consumes external MCP servers (stdio) from SentryBOT."""
from __future__ import annotations

import logging
import re
import threading
from typing import Any, Dict, List, Mapping, Optional

from modules.mcp_client.services.stdio_process import (
    McpClientError,
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
        self._lock = threading.RLock()

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
        with self._lock:
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
        with self._lock:
            names = [str(name)] if name else list(self._conns)
            conns_to_stop = [(n, self._conns.pop(n, None)) for n in names]
        stopped = []
        for n, conn in conns_to_stop:
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

    def select_relevant_tools(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Rank and select the most relevant MCP tools across connected servers using System 1 embeddings or keyword overlap."""
        limit = int(top_k or 0)
        if limit <= 0:
            return []

        candidates: List[Dict[str, Any]] = []
        seen_keys = set()

        try:
            all_res = self.tools(refresh=False)
            servers_map = all_res.get("servers", {}) if isinstance(all_res, dict) else {}
        except Exception:
            servers_map = {}

        if isinstance(servers_map, dict):
            for server_name, tool_list in servers_map.items():
                if not isinstance(tool_list, list):
                    continue
                for item in tool_list:
                    if not isinstance(item, dict):
                        continue
                    t_name = str(item.get("name", "")).strip()
                    key = (str(server_name), t_name)
                    if t_name and key not in seen_keys:
                        seen_keys.add(key)
                        entry = dict(item)
                        entry.setdefault("server", str(server_name))
                        candidates.append(entry)

        with self._lock:
            conns_snapshot = dict(self._conns)
        for server_name, conn in conns_snapshot.items():
            raw_tools = getattr(conn, "tools_cache", None)
            if not raw_tools and hasattr(conn, "tools"):
                try:
                    raw_tools = conn.tools(refresh=False)
                except Exception:
                    raw_tools = []
            for item in raw_tools or []:
                if not isinstance(item, dict):
                    continue
                t_name = str(item.get("name", "")).strip()
                key = (str(server_name), t_name)
                if t_name and key not in seen_keys:
                    seen_keys.add(key)
                    entry = dict(item)
                    entry.setdefault("server", str(server_name))
                    candidates.append(entry)

        if not candidates:
            return []

        cleaned_query = str(query or "").strip()
        if not cleaned_query:
            return candidates[:limit]

        q_tokens = set(re.findall(r"\w+", cleaned_query.lower()))

        embed_engine = None
        query_vec = None
        try:
            from modules.agent_core.services.system1_embed import System1EmbedEngine

            eng = System1EmbedEngine.get_instance()
            if eng is not None and getattr(eng, "is_available", False):
                embed_engine = eng
                query_vec = eng.embed_vector(cleaned_query)
        except Exception:
            embed_engine = None
            query_vec = None

        scored: List[ tuple[float, int, Dict[str, Any]] ] = []
        for idx, tool in enumerate(candidates):
            t_name = str(tool.get("name", "")).strip()
            t_desc = str(tool.get("description", "")).strip()
            doc_text = f"{t_name} {t_desc}".strip()

            doc_tokens = set(re.findall(r"\w+", doc_text.lower()))
            overlap = len(q_tokens & doc_tokens) / max(1, len(q_tokens)) if q_tokens else 0.0
            if t_name.lower() in cleaned_query.lower():
                overlap += 0.5

            sem_score = 0.0
            if embed_engine is not None and query_vec is not None:
                try:
                    import numpy as np

                    t_vec = embed_engine.embed_passage(doc_text)
                    if t_vec is None:
                        t_vec = embed_engine.embed_vector(doc_text)
                    if t_vec is not None:
                        sem_score = float(np.dot(query_vec, t_vec))
                except Exception:
                    sem_score = 0.0

            total_score = (0.75 * sem_score + 0.25 * overlap) if sem_score > 0.0 else overlap
            enriched = dict(tool)
            enriched["score"] = round(float(total_score), 4)
            scored.append((total_score, -idx, enriched))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in scored[:limit]]

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
        with self._lock:
            conns_snapshot = dict(self._conns)
        for name, spec in self._server_specs.items():
            conn = conns_snapshot.get(name)
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
