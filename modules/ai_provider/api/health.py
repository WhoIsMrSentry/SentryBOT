from __future__ import annotations
import logging
import os
from typing import Any, Dict
from fastapi import APIRouter
import requests

logger = logging.getLogger("ollama.api")


def _model_name_matches(available: list[str], wanted: str) -> bool:
    target = str(wanted or "").strip()
    if not target or target == "unknown":
        return True
    candidates = {target, target.split(":", 1)[0], f"{target}:latest"}
    normalized = set()
    for name in available:
        n = str(name or "").strip()
        if not n:
            continue
        normalized.add(n)
        normalized.add(n.split(":", 1)[0])
    return any(c in normalized for c in candidates)


def _normalize_ollama_daemon_base_url(raw: Any) -> tuple[str, str]:
    configured = str(raw or "").strip().rstrip("/")
    value = configured
    lowered = value.lower()
    if (
        not value
        or "@gateway" in lowered
        or lowered in {"http://127.0.0.1:8080", "http://localhost:8080"}
        or lowered.startswith("http://127.0.0.1:8080/")
        or lowered.startswith("http://localhost:8080/")
        or lowered.endswith("/ollama")
        or lowered.endswith("/ollama/chat")
    ):
        value = "http://127.0.0.1:11434"
    return value, configured


def get_health_router(cfg: dict, provider_name: str, model: str) -> APIRouter:
    r = APIRouter(tags=["ollama-health"])

    @r.get("/healthz")
    def healthz():
        info: Dict[str, Any] = {"ok": True, "provider": provider_name, "model": model}
        if provider_name == "ollama":
            base, configured_base = _normalize_ollama_daemon_base_url(cfg.get("ollama", {}).get("base_url", "http://127.0.0.1:11434"))
            info["base_url"] = base
            if configured_base and configured_base != base:
                info["configured_base_url"] = configured_base
                info["base_url_corrected"] = True
            try:
                resp = requests.get(f"{base}/api/tags", timeout=2.0)
                info["daemon_ok"] = resp.status_code == 200
                names: list[str] = []
                if resp.status_code == 200:
                    try:
                        data = resp.json() if resp.content else {}
                    except Exception:
                        data = {}
                    items = data.get("models", []) if isinstance(data, dict) else []
                    for item in items:
                        if isinstance(item, dict) and item.get("name"):
                            names.append(str(item.get("name")))
                info["models_count"] = len(names)
                info["model_available"] = _model_name_matches(names, model)
                info["ok"] = bool(info["daemon_ok"] and info["model_available"])
                if info["daemon_ok"] and not info["model_available"]:
                    info["error"] = "ollama_model_missing"
                    info["expected_model"] = model
                    info["available_models"] = names[:20]
            except Exception as exc:
                info["daemon_ok"] = False
                info["model_available"] = False
                info["ok"] = False
                info["error"] = str(exc)
        elif provider_name == "google_ai_studio":
            gcfg = cfg.get("google_ai_studio", {}) if isinstance(cfg.get("google_ai_studio", {}), dict) else {}
            info["base_url"] = str(gcfg.get("base_url", "https://generativelanguage.googleapis.com"))
            info["api_key_configured"] = bool(str(gcfg.get("api_key", "")).strip() or os.getenv("GOOGLE_API_KEY"))
            info["ok"] = bool(info["api_key_configured"])
        return info

    return r
