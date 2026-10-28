"""Minimal stdio transport for external MCP servers (JSON-RPC over process pipes).

2024-11-05 client side: initialize handshake, notifications/initialized, ping,
tools/list, tools/call. Thread-safe: one reader thread + per-request events.
"""
from __future__ import annotations

import itertools
import json
import logging
import os
import subprocess
import threading
from collections import deque
from typing import Any, Dict, List, Mapping, Optional

logger = logging.getLogger("mcp_client.stdio")

JSONRPC_VERSION = "2.0"


class McpClientError(Exception):
    pass


class ServerNotFound(McpClientError):
    pass


class TransportError(McpClientError):
    pass


class RequestTimeout(McpClientError):
    pass


class RemoteError(McpClientError):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message or f"mcp_error:{code}")
        self.code = int(code)
        self.message = message


class _Pending:
    __slots__ = ("event", "result", "error")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: Any = None
        self.error: Optional[Dict[str, Any]] = None


class StdioMcpConnection:
    """Owns one external MCP server process and multiplexes JSON-RPC requests."""

    def __init__(
        self,
        name: str,
        command: List[str],
        args: Optional[List[str]] = None,
        cwd: Optional[str] = None,
        env: Optional[Mapping[str, str]] = None,
        protocol_version: str = "2024-11-05",
        client_name: str = "sentrybot-mcp-client",
        client_version: str = "0.1.0",
        init_timeout_s: float = 15.0,
        request_timeout_s: float = 20.0,
    ) -> None:
        self.name = str(name)
        self._argv = [str(c) for c in command] + [str(a) for a in (args or [])]
        self._cwd = cwd or None
        self._env_extra = {str(k): str(v) for k, v in (env or {}).items()}
        self.protocol_version = protocol_version
        self.client_name = client_name
        self.client_version = client_version
        self.init_timeout_s = float(init_timeout_s)
        self.request_timeout_s = float(request_timeout_s)

        self.proc: Optional[subprocess.Popen] = None
        self.alive = False
        self.last_error = ""
        self.server_info: Dict[str, Any] = {}
        self.tools_cache: List[Dict[str, Any]] = []

        self._ids = itertools.count(1)
        self._send_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._pending: Dict[int, _Pending] = {}
        self._notifications: deque = deque(maxlen=100)
        self._reader: Optional[threading.Thread] = None
        self._stderr_dumper: Optional[threading.Thread] = None

    # ---- lifecycle ------------------------------------------------------

    def start(self) -> None:
        with self._state_lock:
            if self.alive and self.proc is not None:
                return
            env = os.environ.copy()
            env.setdefault("PYTHONUNBUFFERED", "1")
            env.update(self._env_extra)
            try:
                self.proc = subprocess.Popen(  # noqa: S603
                    self._argv,
                    cwd=self._cwd,
                    env=env,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    bufsize=1,
                )
            except Exception as exc:
                self.last_error = f"spawn_failed:{exc}"
                raise TransportError(self.last_error) from exc
            self.alive = True
            self.last_error = ""
            if self.proc.stderr is not None:
                self._stderr_dumper = threading.Thread(target=self._drain_stderr, daemon=True)
                self._stderr_dumper.start()
            self._reader = threading.Thread(target=self._reader_loop, daemon=True)
            self._reader.start()

    def handshake(self) -> Dict[str, Any]:
        if not self.alive:
            self.start()
        try:
            res = self.request(
                "initialize",
                {
                    "protocolVersion": self.protocol_version,
                    "capabilities": {},
                    "clientInfo": {"name": self.client_name, "version": self.client_version},
                },
                timeout=self.init_timeout_s,
            )
        except McpClientError:
            self.stop()
            raise
        if isinstance(res, dict):
            self.server_info = dict(res.get("serverInfo") or {})
        self.notify("notifications/initialized")
        return self.server_info

    def stop(self) -> None:
        proc = self.proc
        with self._state_lock:
            self.alive = False
        self._fail_all_pending("connection_closed")
        if proc is None:
            return
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass
        try:
            proc.terminate()
            proc.wait(timeout=2.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        self.proc = None
        self.server_info = {}
        self.tools_cache = []

    # ---- protocol -------------------------------------------------------

    def request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None) -> Any:
        if not self.alive or self.proc is None or self.proc.stdin is None:
            raise TransportError(f"not_running:{self.name}")
        rid = next(self._ids)
        pending = _Pending()
        with self._state_lock:
            self._pending[rid] = pending
        msg = {"jsonrpc": JSONRPC_VERSION, "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        try:
            self._send(msg)
            if not pending.event.wait(timeout if timeout is not None else self.request_timeout_s):
                raise RequestTimeout(f"timeout:{self.name}:{method}")
        except Exception:
            with self._state_lock:
                self._pending.pop(rid, None)
            self.alive = False
            raise
        with self._state_lock:
            self._pending.pop(rid, None)
        if pending.error is not None:
            err = pending.error
            raise RemoteError(int(err.get("code", -32603)), str(err.get("message", "remote_error")))
        return pending.result

    def notify(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        msg: Dict[str, Any] = {"jsonrpc": JSONRPC_VERSION, "method": method}
        if params is not None:
            msg["params"] = params
        try:
            self._send(msg)
        except McpClientError:
            raise
        except Exception as exc:
            logger.debug("notify %s failed: %s", method, exc)

    def tools(self, refresh: bool = False) -> List[Dict[str, Any]]:
        if self.tools_cache and not refresh:
            return list(self.tools_cache)
        res = self.request("tools/list", {})
        if isinstance(res, dict):
            tools = res.get("tools")
            if isinstance(tools, list):
                self.tools_cache = [t for t in tools if isinstance(t, dict)]
        return list(self.tools_cache)

    def call(self, tool: str, arguments: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        res = self.request("tools/call", {"name": tool, "arguments": dict(arguments or {})})
        return res if isinstance(res, dict) else {}

    def ping(self) -> bool:
        try:
            self.request("ping", {}, timeout=3.0)
            return True
        except McpClientError:
            return False

    # ---- internals ------------------------------------------------------

    def _send(self, msg: Dict[str, Any]) -> None:
        proc = self.proc
        if proc is None or proc.stdin is None:
            raise TransportError(f"not_running:{self.name}")
        line = json.dumps(msg, ensure_ascii=False) + "\n"
        with self._send_lock:
            try:
                proc.stdin.write(line)
                proc.stdin.flush()
            except Exception as exc:
                self.alive = False
                raise TransportError(f"write_failed:{self.name}:{exc}") from exc

    def _reader_loop(self) -> None:
        proc = self.proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                logger.debug("%s: bad json line", self.name)
                continue
            if not isinstance(msg, dict):
                continue
            self._route(msg)

    def _route(self, msg: Dict[str, Any]) -> None:
        msg_id = msg.get("id")
        if msg_id is None and isinstance(msg.get("method"), str):
            self._notifications.append(msg)
            return
        try:
            rid = int(msg_id)
        except (TypeError, ValueError):
            return
        with self._state_lock:
            pending = self._pending.get(rid)
        if pending is None:
            return
        if isinstance(msg.get("error"), dict):
            pending.error = msg["error"]
        else:
            pending.result = msg.get("result")
        pending.event.set()

    def _fail_all_pending(self, reason: str) -> None:
        with self._state_lock:
            items = list(self._pending.values())
            self._pending.clear()
        for pending in items:
            pending.error = {"code": -32000, "message": reason}
            pending.event.set()

    def _drain_stderr(self) -> None:
        proc = self.proc
        if proc is None or proc.stderr is None:
            return
        try:
            for line in proc.stderr:
                logger.debug("%s stderr: %s", self.name, line.strip()[:300])
        except Exception:
            pass
