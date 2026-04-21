from __future__ import annotations

import os
from typing import Any, Dict

from modules.config_center.agent_yaml_loader import load_agent_config, require_dict_section

_REQUIRED_MODEL = "gemma4:26b"


def _to_float(raw: Any, fallback: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


def _pick_model(agent_cfg: Dict[str, Any], llm_cfg: Dict[str, Any], ollama_cfg: Dict[str, Any]) -> str:
    candidates = (
        agent_cfg.get("model"),
        llm_cfg.get("model"),
        llm_cfg.get("primary_model"),
        ollama_cfg.get("model"),
    )
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text:
            return text
    return ""


def _normalize_base_url(raw: Any) -> str:
    return str(raw or "").strip().rstrip("/")


def _enforce_policy(cfg: Dict[str, Any]) -> Dict[str, Any]:
    agent_cfg = require_dict_section(cfg, "agent")
    llm_cfg = require_dict_section(cfg, "llm")
    ollama_cfg = cfg.get("ollama", {}) if isinstance(cfg.get("ollama", {}), dict) else {}

    provider = str(llm_cfg.get("provider", "ollama")).strip().lower() or "ollama"
    if provider != "ollama":
        raise ValueError("Only ollama provider is allowed in strict single-source mode")

    model = _pick_model(agent_cfg, llm_cfg, ollama_cfg)
    if model != _REQUIRED_MODEL:
        raise ValueError(f"Single-model policy requires model '{_REQUIRED_MODEL}', got '{model or '<empty>'}'")

    base_url = _normalize_base_url(
        agent_cfg.get("ollama_base_url")
        or llm_cfg.get("base_url")
        or ollama_cfg.get("base_url")
        or os.getenv("AGENT_OLLAMA_BASE_URL")
        or "http://localhost:11434"
    )
    if not base_url:
        raise ValueError("agent.ollama_base_url is required")

    request_timeout = _to_float(
        agent_cfg.get("request_timeout", ollama_cfg.get("request_timeout", 60.0)),
        60.0,
    )

    agent_cfg["model"] = _REQUIRED_MODEL
    agent_cfg["ollama_base_url"] = base_url
    agent_cfg["request_timeout"] = request_timeout

    llm_cfg["provider"] = "ollama"
    llm_cfg["single_model_mode"] = True
    llm_cfg["model"] = _REQUIRED_MODEL
    llm_cfg["primary_model"] = _REQUIRED_MODEL
    llm_cfg["base_url"] = base_url
    llm_cfg["clm_fallback_enabled"] = False
    llm_cfg["clm_fallback_model"] = ""
    llm_cfg["fallback_on_missing_model"] = False
    llm_cfg["fallback_on_error"] = False

    cfg["ollama"] = {
        **ollama_cfg,
        "base_url": base_url,
        "model": _REQUIRED_MODEL,
        "request_timeout": request_timeout,
    }
    cfg["agent"] = agent_cfg
    cfg["llm"] = llm_cfg
    return cfg


def load_config(path: str | os.PathLike | None = None) -> Dict[str, Any]:
    cfg = load_agent_config(path)

    if not isinstance(cfg.get("tri_layer", {}), dict):
        cfg["tri_layer"] = {}
    if not isinstance(cfg.get("safety", {}), dict):
        cfg["safety"] = {}

    return _enforce_policy(cfg)
