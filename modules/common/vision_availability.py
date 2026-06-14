"""Shared helpers for live camera vs remote vision cache availability."""

from __future__ import annotations

from typing import Any, Dict, Optional


def _parse_json(resp) -> Dict[str, Any]:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def camera_live_available(base_url: str, *, timeout_s: float = 0.5) -> bool:
    """True when gateway camera healthz reports a live frame."""
    try:
        import requests

        from modules.gateway.url import gateway_url

        resp = requests.get(gateway_url(base_url, "/camera/healthz"), timeout=timeout_s)
        if resp.status_code != 200:
            return False
        data = _parse_json(resp)
        return bool(data.get("ok")) and not bool(data.get("gave_up", False))
    except Exception:
        return False


def remote_vision_cache_available(base_url: str, *, timeout_s: float = 0.6) -> bool:
    """True when VLM bridge has remote-ingested context or detection cache."""
    try:
        import requests

        from modules.gateway.url import gateway_url

        ctx = requests.get(gateway_url(base_url, "/vlm/context/latest"), timeout=timeout_s)
        if ctx.status_code == 200:
            data = _parse_json(ctx)
            if data.get("available"):
                return True
        results = requests.get(
            gateway_url(base_url, "/vlm/results/latest"),
            params={"limit": 1},
            timeout=timeout_s,
        )
        if results.status_code == 200:
            data = _parse_json(results)
            items = data.get("results")
            if isinstance(items, list) and items:
                return True
    except Exception:
        return False
    return False


def vision_input_available(base_url: str, *, timeout_s: float = 0.6) -> bool:
    """Live camera OR remote vision cache is usable for agent/VLM tools."""
    if camera_live_available(base_url, timeout_s=min(timeout_s, 0.5)):
        return True
    return remote_vision_cache_available(base_url, timeout_s=timeout_s)
