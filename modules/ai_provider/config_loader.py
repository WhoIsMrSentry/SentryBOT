from __future__ import annotations

import os
from typing import Any, Dict

from modules.common.config_loader import deep_merge, load_agent_config, require_dict_section, DEFAULT_GEMINI_MODEL

_REQUIRED_MODEL = "qwen3.5:9b"
_GOOGLE_PROVIDERS = frozenset({"google", "google_ai_studio", "gemini"})

_DEFAULT_CFG: Dict[str, Any] = {
    "server": {"host": "0.0.0.0", "port": 8099},
    "llm": {"provider": "ollama", "single_model_mode": True},
    "ollama": {"base_url": "http://127.0.0.1:11434", "model": _REQUIRED_MODEL, "request_timeout": 60.0},
    "google_ai_studio": {
        "api_key": "",
        "model": DEFAULT_GEMINI_MODEL,
        "base_url": "https://generativelanguage.googleapis.com",
        "request_timeout": 45.0,
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
    value = str(raw or "").strip().rstrip("/")
    env_override = str(os.getenv("SENTRYBOT_OLLAMA_BASE_URL") or os.getenv("OLLAMA_BASE_URL") or "").strip().rstrip("/")
    if env_override:
        value = env_override
    lowered = value.lower()
    # The gateway usually runs on 8080. It is not the Ollama daemon.
    # Accidentally probing http://127.0.0.1:8080/api/tags creates false 404/self-call failures.
    if (
        not value
        or "@gateway" in lowered
        or lowered in {"http://127.0.0.1:8080", "http://localhost:8080"}
        or lowered.startswith("http://127.0.0.1:8080/")
        or lowered.startswith("http://localhost:8080/")
        or lowered.endswith("/ollama")
        or lowered.endswith("/ollama/chat")
    ):
        return "http://127.0.0.1:11434"
    return value


def load_config(config_path: str | None = None) -> Dict[str, Any]:
    root_cfg = load_agent_config(config_path)

    agent_cfg = require_dict_section(root_cfg, "agent")
    llm_cfg = require_dict_section(root_cfg, "llm")
    ollama_global = require_dict_section(root_cfg, "ollama")
    service_cfg = require_dict_section(root_cfg, "ollama_service")
    google_global = root_cfg.get("google_ai_studio", {})
    if not isinstance(google_global, dict):
        google_global = {}

    provider = str(llm_cfg.get("provider", "")).strip().lower() or "ollama"
    request_timeout = _to_float(
        ollama_global.get("request_timeout", agent_cfg.get("request_timeout", 60.0)),
        60.0,
    )

    if provider in _GOOGLE_PROVIDERS:
        model = (
            str(google_global.get("model", "")).strip()
            or _pick_model(agent_cfg, llm_cfg, ollama_global)
            or DEFAULT_GEMINI_MODEL
        )
        google_timeout = _to_float(google_global.get("request_timeout", request_timeout), request_timeout)
        core_cfg: Dict[str, Any] = {
            "llm": {
                "provider": "google_ai_studio",
                "single_model_mode": True,
                "model": model,
                "primary_model": model,
            },
            "google_ai_studio": {
                **google_global,
                "model": model,
                "request_timeout": google_timeout,
            },
            "ollama": {
                "base_url": _normalize_base_url(
                    agent_cfg.get("ollama_base_url")
                    or ollama_global.get("base_url")
                    or os.getenv("SENTRYBOT_OLLAMA_BASE_URL")
                    or os.getenv("OLLAMA_BASE_URL")
                    or os.getenv("AGENT_OLLAMA_BASE_URL")
                    or "http://127.0.0.1:11434"
                ),
                "model": _REQUIRED_MODEL,
                "request_timeout": request_timeout,
            },
        }
    else:
        model = _pick_model(agent_cfg, llm_cfg, ollama_global)
        if model != _REQUIRED_MODEL:
            raise ValueError(
                f"Ollama profile requires model '{_REQUIRED_MODEL}', got '{model or '<empty>'}'"
            )

        base_url = _normalize_base_url(
            agent_cfg.get("ollama_base_url")
            or llm_cfg.get("base_url")
            or ollama_global.get("base_url")
            or os.getenv("SENTRYBOT_OLLAMA_BASE_URL")
            or os.getenv("OLLAMA_BASE_URL")
            or os.getenv("AGENT_OLLAMA_BASE_URL")
            or "http://127.0.0.1:11434"
        )
        if not base_url:
            raise ValueError("agent.ollama_base_url is required")

        core_cfg = {
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
            "google_ai_studio": google_global,
        }

    merged = deep_merge(_DEFAULT_CFG, service_cfg)
    merged = deep_merge(merged, core_cfg)

    if provider in _GOOGLE_PROVIDERS:
        trans = merged.get("translation", {})
        if isinstance(trans, dict):
            merged["translation"] = {**trans, "enabled": False}

    google_cfg = merged.get("google_ai_studio", {})
    if isinstance(google_cfg, dict):
        key = str(google_cfg.get("api_key", "")).strip()
        if not key:
            env_key = str(os.getenv("GOOGLE_API_KEY", "")).strip()
            if env_key:
                google_cfg = {**google_cfg, "api_key": env_key}
                merged["google_ai_studio"] = google_cfg

    return merged
