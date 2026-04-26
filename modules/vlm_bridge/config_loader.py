from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from modules.config_center.agent_yaml_loader import deep_merge, load_agent_config, require_dict_section

DEFAULT_CONFIG: Dict[str, Any] = {
    "server": {"host": "0.0.0.0", "port": 8099},
    "vision": {
        "processing_mode": "local",  # local | remote
        "camera_source": "http://127.0.0.1:8080/camera/video",
        "blind_mode": {"enabled": False, "interval_seconds": 5.0},
        "confidence_threshold": 0.5,
        "face_match": {
            "ratio_test": 0.72,
            "min_good_matches": 10,
            "min_score": 0.15,
        },
        "follow": {
            "enabled": True,
            "track_interval_s": 0.12,
            "pan_gain_deg": 50,
            "tilt_gain_deg": 32,
            "center_pan": 90,
            "center_tilt": 90,
            "min_pan": 35,
            "max_pan": 145,
            "min_tilt": 65,
            "max_tilt": 125,
            "max_lost_frames": 18,
        },
    },
    "remote": {
        "auth_token": "changeme",  # Override in deployment
        "accept_results": True,
    },
    "llm": {
        "provider": "ollama",  # ollama | google_ai_studio
        "single_model_mode": True,
        "primary_model": "qwen3.5:9b",
        "clm_fallback_enabled": True,
        "clm_fallback_model": "qwen3.5:9b",
        "fallback_on_missing_model": True,
        "fallback_on_error": True,
    },
    "ollama": {
        "endpoint": "http://localhost:8080/ollama/chat",
        "model": "qwen3.5:9b",
        "timeout": 12.0,
        "num_predict": 160,
    },
    "speak": {
        "endpoint": "http://localhost:8083/speak/say",
    },
    "actions": {
        "endpoint": "http://localhost:8080/autonomy/apply_actions",
        "default_apply": False,
        "timeout": 1.5,
    },
}

_REQUIRED_MODEL = "qwen3.5:9b"


def _to_float(raw: Any, fallback: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


def _normalize_ollama_base_url(raw: Any) -> str:
    value = str(raw or "").strip().rstrip("/")
    if not value:
        return ""
    lowered = value.lower()
    for suffix in ("/api/chat", "/api/generate", "/api/tags", "/ollama/chat"):
        if lowered.endswith(suffix):
            return value[: -len(suffix)].rstrip("/")
    return value


def _to_vlm_chat_endpoint(raw: Any) -> str:
    endpoint = str(raw or "").strip()
    if not endpoint:
        return ""
    lower = endpoint.rstrip("/").lower()
    if lower.endswith("/api/tags"):
        return endpoint[: -len("/api/tags")] + "/api/chat"
    if lower.endswith("/api/chat") or lower.endswith("/api/generate") or lower.endswith("/ollama/chat"):
        return endpoint
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        return endpoint.rstrip("/") + "/api/chat"
    return endpoint


def _resolve_agent_cfg_path(base_dir: Optional[str]) -> Optional[str]:
    if not base_dir:
        return None

    base = Path(base_dir)
    if base.is_file():
        return str(base)

    return str(base / "config" / "agent.yaml")


def _enforce_single_model_policy(cfg: Dict[str, Any], root_cfg: Dict[str, Any]) -> Dict[str, Any]:
    root_agent = require_dict_section(root_cfg, "agent")
    root_llm = require_dict_section(root_cfg, "llm")
    root_ollama = require_dict_section(root_cfg, "ollama")

    provider = str(root_llm.get("provider", "")).strip().lower()
    if provider != "ollama":
        raise ValueError("vlm_bridge supports only ollama provider in strict mode")

    model_candidates = (
        root_agent.get("model"),
        root_llm.get("model"),
        root_llm.get("primary_model"),
        root_ollama.get("model"),
    )
    model = ""
    for candidate in model_candidates:
        text = str(candidate or "").strip()
        if text:
            model = text
            break
    if model != _REQUIRED_MODEL:
        raise ValueError(f"Single-model policy requires model '{_REQUIRED_MODEL}', got '{model or '<empty>'}'")

    base_url = _normalize_ollama_base_url(
        root_agent.get("ollama_base_url")
        or root_llm.get("base_url")
        or root_ollama.get("base_url")
        or os.getenv("AGENT_OLLAMA_BASE_URL")
        or "http://localhost:11434"
    )
    if not base_url:
        raise ValueError("agent.ollama_base_url is required")

    llm_cfg = cfg.setdefault("llm", {})
    ollama_cfg = cfg.setdefault("ollama", {})

    llm_cfg["provider"] = "ollama"
    llm_cfg["single_model_mode"] = True
    llm_cfg["primary_model"] = _REQUIRED_MODEL
    llm_cfg["model"] = _REQUIRED_MODEL
    llm_cfg["clm_fallback_enabled"] = False
    llm_cfg["clm_fallback_model"] = ""
    llm_cfg["fallback_on_missing_model"] = False
    llm_cfg["fallback_on_error"] = False

    ollama_cfg["endpoint"] = _to_vlm_chat_endpoint(base_url)
    ollama_cfg["model"] = _REQUIRED_MODEL
    ollama_cfg["timeout"] = _to_float(ollama_cfg.get("timeout", root_ollama.get("request_timeout", 12.0)), 12.0)
    cfg["ollama"] = ollama_cfg
    cfg["llm"] = llm_cfg
    return cfg


def load_config(base_dir: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    agent_cfg_path = _resolve_agent_cfg_path(base_dir)
    root_cfg = load_agent_config(agent_cfg_path)
    vlm_cfg = require_dict_section(root_cfg, "vlm_bridge")

    cfg: Dict[str, Any] = deep_merge(DEFAULT_CONFIG, vlm_cfg)
    if overrides:
        cfg = deep_merge(cfg, {k: v for k, v in overrides.items() if v is not None})

    return _enforce_single_model_policy(cfg, root_cfg)
