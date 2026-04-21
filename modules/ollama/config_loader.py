from __future__ import annotations

import os
from typing import Any, Dict

from modules.config_center.agent_yaml_loader import deep_merge, load_agent_config, require_dict_section

_REQUIRED_MODEL = "gemma4:26b"

_DEFAULT_CFG: Dict[str, Any] = {
    "server": {"host": "0.0.0.0", "port": 8099},
    "llm": {"provider": "ollama", "single_model_mode": True},
    "ollama": {"base_url": "http://localhost:11434", "model": _REQUIRED_MODEL, "request_timeout": 60.0},
    "google_ai_studio": {
        "api_key": "",
        "model": "gemini-1.5-flash",
        "base_url": "https://generativelanguage.googleapis.com",
        "request_timeout": 60.0,
    },
    "persona": {"default": "sentry", "dir": "modules/ollama/config/personalities"},
    "actions": {
        "endpoint": "http://localhost:8080/autonomy/apply_actions",
        "default_apply": True,
        "timeout": 1.5,
    },
    "translation": {
        "enabled": True,
        "default_source_lang": "tr",
        "model": "",
        "cache_size": 128,
    },
}


def _to_float(raw: Any, fallback: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


def _pick_model(agent_cfg: Dict[str, Any], llm_cfg: Dict[str, Any], ollama_cfg: Dict[str, Any]) -> str:
    for candidate in (
        agent_cfg.get("model"),
        llm_cfg.get("model"),
        llm_cfg.get("primary_model"),
        ollama_cfg.get("model"),
    ):
        value = str(candidate or "").strip()
        if value:
            return value
    return ""


def _normalize_base_url(raw: Any) -> str:
    return str(raw or "").strip().rstrip("/")


def load_config(config_path: str | None = None) -> Dict[str, Any]:
    root_cfg = load_agent_config(config_path)

    agent_cfg = require_dict_section(root_cfg, "agent")
    llm_cfg = require_dict_section(root_cfg, "llm")
    ollama_global = require_dict_section(root_cfg, "ollama")
    service_cfg = require_dict_section(root_cfg, "ollama_service")

    provider = str(llm_cfg.get("provider", "")).strip().lower()
    if provider != "ollama":
        raise ValueError("Only ollama provider is allowed for ollama module")

    model = _pick_model(agent_cfg, llm_cfg, ollama_global)
    if model != _REQUIRED_MODEL:
        raise ValueError(f"Single-model policy requires model '{_REQUIRED_MODEL}', got '{model or '<empty>'}'")

    base_url = _normalize_base_url(
        agent_cfg.get("ollama_base_url")
        or llm_cfg.get("base_url")
        or ollama_global.get("base_url")
        or os.getenv("AGENT_OLLAMA_BASE_URL")
        or "http://localhost:11434"
    )
    if not base_url:
        raise ValueError("agent.ollama_base_url is required")

    request_timeout = _to_float(
        ollama_global.get("request_timeout", agent_cfg.get("request_timeout", 60.0)),
        60.0,
    )

    strict_core_cfg: Dict[str, Any] = {
        "llm": {
            "provider": "ollama",
            "single_model_mode": True,
            "model": _REQUIRED_MODEL,
            "primary_model": _REQUIRED_MODEL,
            "base_url": base_url,
        },
        "ollama": {
            "base_url": base_url,
            "model": _REQUIRED_MODEL,
            "request_timeout": request_timeout,
        },
    }

    merged = deep_merge(_DEFAULT_CFG, service_cfg)
    merged = deep_merge(merged, strict_core_cfg)
    return merged
