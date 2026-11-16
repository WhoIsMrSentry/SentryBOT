"""Shared helpers for live camera vs remote vision cache availability."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Tuple

import requests

_REAL_REQUESTS_GET = requests.get
_SESSION_LOCK = threading.Lock()
_SESSION: requests.Session | None = None
_CACHE_LOCK = threading.Lock()
_CACHE: Dict[Tuple[str, str], Tuple[float, bool]] = {}
DEFAULT_CACHE_TTL_S = 1.0


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        with _SESSION_LOCK:
            if _SESSION is None:
                _SESSION = requests.Session()
    return _SESSION


def clear_vision_cache() -> None:
    """Clear short-lived HTTP probe cache."""
    with _CACHE_LOCK:
        _CACHE.clear()


def _http_get(url: str, *, timeout: float, params: Dict[str, Any] | None = None):
    if requests.get is not _REAL_REQUESTS_GET:
        kwargs: Dict[str, Any] = {"timeout": timeout}
        if params is not None:
            kwargs["params"] = params
        return requests.get(url, **kwargs)
    return _get_session().get(url, params=params, timeout=timeout)


def _use_cache(cache_ttl_s: float) -> bool:
    return cache_ttl_s > 0 and requests.get is _REAL_REQUESTS_GET


def _parse_json(resp) -> Dict[str, Any]:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def camera_live_available(
    base_url: str,
    *,
    timeout_s: float = 0.5,
    cache_ttl_s: float = DEFAULT_CACHE_TTL_S,
) -> bool:
    """True when gateway camera healthz reports a live frame."""
    key = ("camera", base_url.rstrip("/"))
    now = time.monotonic()
    if _use_cache(cache_ttl_s):
        with _CACHE_LOCK:
            cached = _CACHE.get(key)
            if cached is not None and (now - cached[0]) < cache_ttl_s:
                return cached[1]

    available = False
    try:
        from .url_utils import gateway_url

        resp = _http_get(gateway_url(base_url, "/camera/healthz"), timeout=timeout_s)
        if resp.status_code == 200:
            data = _parse_json(resp)
            available = bool(data.get("ok")) and not bool(data.get("gave_up", False))
    except Exception:
        available = False

    if _use_cache(cache_ttl_s):
        with _CACHE_LOCK:
            _CACHE[key] = (time.monotonic(), available)
    return available


def remote_vision_cache_available(
    base_url: str,
    *,
    timeout_s: float = 0.6,
    cache_ttl_s: float = DEFAULT_CACHE_TTL_S,
) -> bool:
    """True when VLM bridge has remote-ingested context or detection cache."""
    key = ("remote", base_url.rstrip("/"))
    now = time.monotonic()
    if _use_cache(cache_ttl_s):
        with _CACHE_LOCK:
            cached = _CACHE.get(key)
            if cached is not None and (now - cached[0]) < cache_ttl_s:
                return cached[1]

    available = False
    try:
        from .url_utils import gateway_url

        ctx = _http_get(gateway_url(base_url, "/vlm/context/latest"), timeout=timeout_s)
        if ctx.status_code == 200:
            data = _parse_json(ctx)
            if data.get("available"):
                available = True
        if not available:
            results = _http_get(
                gateway_url(base_url, "/vlm/results/latest"),
                params={"limit": 1},
                timeout=timeout_s,
            )
            if results.status_code == 200:
                data = _parse_json(results)
                items = data.get("results")
                if isinstance(items, list) and items:
                    available = True
    except Exception:
        available = False

    if _use_cache(cache_ttl_s):
        with _CACHE_LOCK:
            _CACHE[key] = (time.monotonic(), available)
    return available


def vision_input_available(
    base_url: str,
    *,
    timeout_s: float = 0.6,
    cache_ttl_s: float = DEFAULT_CACHE_TTL_S,
) -> bool:
    """Live camera OR remote vision cache is usable for agent/VLM tools."""
    if camera_live_available(base_url, timeout_s=min(timeout_s, 0.5), cache_ttl_s=cache_ttl_s):
        return True
    return remote_vision_cache_available(base_url, timeout_s=timeout_s, cache_ttl_s=cache_ttl_s)
