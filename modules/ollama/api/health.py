from __future__ import annotations
import logging
import os
from typing import Any, Dict
from fastapi import APIRouter
import requests

logger = logging.getLogger("ollama.api")


def get_health_router(cfg: dict, provider_name: str, model: str) -> APIRouter:
    r = APIRouter(tags=["ollama-health"])

    @r.get("/healthz")
    def healthz():
        info: Dict[str, Any] = {"ok": True, "provider": provider_name, "model": model}
        if provider_name == "ollama":
            base = str(cfg.get("ollama", {}).get("base_url", "http://127.0.0.1:11434")).rstrip("/")
            info["base_url"] = base
            try:
                resp = requests.get(f"{base}/api/tags", timeout=2.0)
                info["daemon_ok"] = resp.status_code == 200
                info["ok"] = bool(info["daemon_ok"])
            except Exception as exc:
                info["daemon_ok"] = False
                info["ok"] = False
                info["error"] = str(exc)
        elif provider_name == "google_ai_studio":
            gcfg = cfg.get("google_ai_studio", {}) if isinstance(cfg.get("google_ai_studio", {}), dict) else {}
            info["base_url"] = str(gcfg.get("base_url", "https://generativelanguage.googleapis.com"))
            info["api_key_configured"] = bool(str(gcfg.get("api_key", "")).strip() or os.getenv("GOOGLE_API_KEY"))
            info["ok"] = bool(info["api_key_configured"])
        return info

    return r
