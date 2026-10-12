"""Loopback-first HTTP bind host for standalone module servers.

``server.host`` in YAML stays the config key. A module environment variable
overrides that value when it is set, so a Pi image can opt into ``0.0.0.0``
without a code change.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

DEFAULT_BIND_HOST = "127.0.0.1"


def resolve_bind_host(
    configured: object | None = None,
    *env_names: str,
    default: str = DEFAULT_BIND_HOST,
) -> str:
    """Return the bind host: env override, then config, then loopback."""
    for name in env_names:
        raw = str(os.getenv(name, "")).strip()
        if raw:
            return raw
    value = str(configured).strip() if configured is not None else ""
    return value or default


def apply_bind_host(cfg: dict[str, Any], *env_names: str, default: str = DEFAULT_BIND_HOST) -> dict[str, Any]:
    """Write the resolved host back onto ``cfg['server']['host']``."""
    server = cfg.get("server")
    if not isinstance(server, Mapping):
        server = {}
    else:
        server = dict(server)
    server["host"] = resolve_bind_host(server.get("host"), *env_names, default=default)
    cfg["server"] = server
    return cfg
