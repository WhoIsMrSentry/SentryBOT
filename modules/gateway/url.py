"""Resolve gateway base URL for loopback HTTP calls between modules."""
from __future__ import annotations

import os
import re
from typing import Any, Dict, Mapping, Optional

_LOOPBACK_PREFIXES = (
    "http://localhost:",
    "http://127.0.0.1:",
    "http://0.0.0.0:",
)
_GATEWAY_PATH_RE = re.compile(r"^@gateway(?=/|$)")


def gateway_base_from_agent_cfg(cfg: Mapping[str, Any], *, port: int = 8080) -> str:
    """Read gateway base from an already-loaded agent.yaml mapping (no reload)."""
    actions = cfg.get("actions", {}) if isinstance(cfg.get("actions", {}), dict) else {}
    explicit = str(actions.get("gateway_base_url", "") or "").strip().rstrip("/")
    if explicit:
        return explicit

    for section in ("gateway", "server"):
        block = cfg.get(section, {})
        if isinstance(block, dict):
            try:
                port = int(block.get("port", port))
            except (TypeError, ValueError):
                pass
            host = str(block.get("host", "127.0.0.1") or "127.0.0.1").strip()
            if host in ("0.0.0.0", "::"):
                host = "127.0.0.1"
            return f"http://{host}:{int(port)}"

    return f"http://127.0.0.1:{int(port)}"


def resolve_gateway_base_url(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    port: int = 8080,
    started: Optional[Mapping[str, Any]] = None,
) -> str:
    if started is not None:
        explicit = str(started.get("gateway_base_url", "") or "").strip().rstrip("/")
        if explicit:
            return explicit

    env = str(os.environ.get("SENTRY_GATEWAY_URL", "") or "").strip().rstrip("/")
    if env:
        return env

    if cfg is not None:
        explicit = str(cfg.get("gateway_base_url", "") or "").strip().rstrip("/")
        if explicit:
            return explicit
        return gateway_base_from_agent_cfg(cfg, port=port)

    try:
        from modules.config_center.agent_yaml_loader import load_agent_config  # type: ignore

        return gateway_base_from_agent_cfg(load_agent_config())
    except Exception:
        pass

    return f"http://127.0.0.1:{int(port)}"


def gateway_url(base: str, path: str) -> str:
    return f"{str(base).rstrip('/')}/{str(path).lstrip('/')}"


def resolve_config_url(value: str, gateway_base: Optional[str] = None) -> str:
    """Resolve @gateway/... aliases and loopback :8080 URLs to the active gateway base."""
    raw = str(value or "").strip()
    if not raw:
        return raw
    base = str(gateway_base or resolve_gateway_base_url()).rstrip("/")

    if _GATEWAY_PATH_RE.match(raw):
        path = raw[len("@gateway") :]
        return gateway_url(base, path or "/")

    for prefix in _LOOPBACK_PREFIXES:
        if raw.lower().startswith(prefix):
            suffix = raw.split(":", 2)[-1]
            if "/" in suffix:
                path = "/" + suffix.split("/", 1)[1]
            else:
                path = ""
            return gateway_url(base, path)
    return raw


def rewrite_loopback_urls(obj: Any, gateway_base: str) -> Any:
    """Recursively rewrite @gateway/ and loopback :8080 URLs in nested config dicts."""
    base = str(gateway_base or "").rstrip("/")
    if isinstance(obj, str):
        return resolve_config_url(obj, base)
    if isinstance(obj, dict):
        return {k: rewrite_loopback_urls(v, base) for k, v in obj.items()}
    if isinstance(obj, list):
        return [rewrite_loopback_urls(v, base) for v in obj]
    return obj


def patch_service_endpoints(endpoints: Dict[str, Any], gateway_base: str) -> Dict[str, Any]:
    """Rewrite autonomy-style endpoint map to use a single gateway base."""
    base = str(gateway_base or "").rstrip("/")
    if not base:
        return endpoints

    service_paths = {
        "arduino": "/arduino",
        "neopixel": "/neopixel",
        "speak": "/speak",
        "ollama": "/ollama",
        "speech": "/speech",
        "interactions": "/interactions",
        "oled_faces": "/oled_faces",
        "state_manager": "/state",
        "animate": "/animate",
        "vlm": "/vlm",
        "vision": "/vlm",
        "camera": "/camera",
        "notifier": "/notify",
        "autonomy": "/autonomy",
        "agent_core": "/agent",
    }

    out = dict(endpoints or {})
    for key, path_suffix in service_paths.items():
        out[key] = f"{base}{path_suffix}"
    return out
