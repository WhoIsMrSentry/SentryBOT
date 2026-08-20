"""Resolve Google AI Studio API key from agent.yaml + environment."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

from modules.ai_provider.services.clients import _sanitize_google_api_key

logger = logging.getLogger("config_center.google_keys")


def resolve_google_api_key(cfg: Dict[str, Any]) -> str:
    google_cfg = cfg.get("google_ai_studio", {})
    if not isinstance(google_cfg, dict):
        google_cfg = {}
    key = _sanitize_google_api_key(google_cfg.get("api_key", ""))
    if not key:
        key = _sanitize_google_api_key(os.getenv("GOOGLE_API_KEY", ""))
    return key


def inject_google_api_key(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Attach resolved key to cfg without wiping an existing valid value."""
    key = resolve_google_api_key(cfg)
    if not key:
        llm = cfg.get("llm", {}) if isinstance(cfg.get("llm", {}), dict) else {}
        provider = str(llm.get("provider", "")).strip().lower()
        if provider in {"google", "google_ai_studio", "gemini"}:
            logger.warning(
                "runtime_profile uses Google but no API key found — set google_ai_studio.api_key "
                "in config/agent.yaml or export GOOGLE_API_KEY before starting the robot"
            )
        return cfg
    google_cfg = cfg.get("google_ai_studio", {})
    if not isinstance(google_cfg, dict):
        google_cfg = {}
    else:
        google_cfg = dict(google_cfg)
    if not _sanitize_google_api_key(google_cfg.get("api_key", "")):
        google_cfg["api_key"] = key
    cfg["google_ai_studio"] = google_cfg
    return cfg
