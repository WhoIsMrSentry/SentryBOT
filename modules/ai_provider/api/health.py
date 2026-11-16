"""Ollama health endpoint for the AI provider module.

Single canonical ``get_health_router`` implementation. Six historical
shadowing definitions and four dead URL-normalizer generations
(batch06c/d/k/l/m) were removed during the code audit (consolidation
#6); only the final override was kept.
"""

from __future__ import annotations

from typing import Optional
import requests

from modules.common.ollama_url import (
    default_ollama_base_url as _default_base_url,
    unwrap_url as _unwrap_url,
    normalize_ollama_url as _normalize_base_url,
)


def _extract_model_names(data):
    if not isinstance(data, dict):
        return []

    raw_models = data.get("models")

    if not isinstance(raw_models, list):
        return []

    names = []

    for item in raw_models:
        name = None

        if isinstance(item, dict):
            name = item.get("name") or item.get("model")
        elif isinstance(item, str):
            name = item

        if name:
            names.append(str(name).strip())

    return [name for name in names if name]

def get_health_router(config=None, provider="ollama", model="", *args, runtime: Optional[dict] = None, **kwargs):
    from fastapi import APIRouter

    router = APIRouter()

    configured_base_url = None

    if isinstance(config, dict):
        ollama_cfg = config.get("ollama")

        if isinstance(ollama_cfg, dict):
            configured_base_url = _unwrap_url(ollama_cfg.get("base_url"))

    if not configured_base_url:
        configured_base_url = _default_base_url()

    base_url = _normalize_base_url(configured_base_url)
    base_url_corrected = base_url != configured_base_url
    requested_model = str(model or "").strip()

    @router.get("/healthz")
    def healthz():
        active_model = str((runtime or {}).get("model") or requested_model).strip()
        active_provider = str(provider or "").strip().lower()
        client = (runtime or {}).get("client")
        breaker_info = client.circuit_state() if hasattr(client, "circuit_state") else None
        tags_url = base_url.rstrip("/") + "/api/tags"

        payload = {
            "ok": False,
            "provider": provider,
            "model": active_model,
            "base_url": base_url,
            "configured_base_url": configured_base_url,
            "base_url_corrected": base_url_corrected,
            "url": tags_url,
            "daemon_ok": False,
            "model_available": False,
            "available_models": [],
        }
        if breaker_info is not None:
            payload["circuit_breaker"] = breaker_info

        if active_provider != "ollama":
            payload["error"] = "provider_disabled"
            return payload

        try:
            response = requests.get(tags_url, timeout=2.0)
            status_code = getattr(response, "status_code", None)

            payload["status_code"] = status_code

            try:
                status_int = int(status_code)
            except Exception:
                status_int = 200

            daemon_ok = status_int < 500
            payload["daemon_ok"] = daemon_ok

            try:
                response_data = response.json()
            except Exception:
                response_data = {}

            payload["response"] = response_data

            model_names = _extract_model_names(response_data)
            payload["available_models"] = model_names

            model_available = bool(active_model) and active_model in model_names
            payload["model_available"] = model_available

            if daemon_ok and model_available:
                payload["ok"] = True
            elif daemon_ok and not model_available:
                payload["ok"] = False
                payload["error"] = "ollama_model_missing"
            else:
                payload["ok"] = False
                payload["error"] = "ollama_daemon_unavailable"

        except Exception as exc:
            payload["ok"] = False
            payload["daemon_ok"] = False
            payload["model_available"] = False
            payload["error"] = "ollama_daemon_unavailable"
            payload["exception"] = str(exc)

        return payload

    @router.get("/health")
    def health():
        return healthz()

    return router
