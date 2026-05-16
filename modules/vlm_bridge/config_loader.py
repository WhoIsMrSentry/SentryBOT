from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from modules.config_center.agent_yaml_loader import deep_merge, load_agent_config, require_dict_section
from modules.config_center.gemini_model import DEFAULT_GEMINI_MODEL

DEFAULT_CONFIG: Dict[str, Any] = {
    "server": {"host": "0.0.0.0", "port": 8101},
    "vision": {
        "processing_mode": "remote",
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
        "auth_token": "changeme",
        "accept_results": True,
    },
    "llm": {
        "provider": "ollama",
        "single_model_mode": True,
        "primary_model": "qwen3.5:9b",
        "clm_fallback_enabled": False,
        "clm_fallback_model": "",
        "fallback_on_missing_model": False,
        "fallback_on_error": False,
    },
    "ollama": {
        "endpoint": "http://localhost:8080/ollama/chat",
        "model": "qwen3.5:9b",
        "timeout": 12.0,
        "num_predict": 160,
    },
    "vision_llm": {
        "enabled": True,
        "provider": "ollama",
    },
    "google_ai_studio": {
        "api_key": "",
        "model": DEFAULT_GEMINI_MODEL,
        "base_url": "https://generativelanguage.googleapis.com",
        "request_timeout": 45.0,
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

_REQUIRED_OLLAMA_MODEL = "qwen3.5:9b"
_GOOGLE_PROVIDERS = frozenset({"google", "google_ai_studio", "gemini"})


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


def _pick_model(agent_cfg: Dict[str, Any], llm_cfg: Dict[str, Any], ollama_cfg: Dict[str, Any]) -> str:
    for candidate in (
        agent_cfg.get("model"),
        llm_cfg.get("model"),
        llm_cfg.get("primary_model"),
        ollama_cfg.get("model"),
    ):
        text = str(candidate or "").strip()
        if text:
            return text
    return ""


def _enforce_google_policy(cfg: Dict[str, Any], root_cfg: Dict[str, Any]) -> Dict[str, Any]:
    root_agent = require_dict_section(root_cfg, "agent")
    root_llm = require_dict_section(root_cfg, "llm")
    root_google = root_cfg.get("google_ai_studio", {})
    if not isinstance(root_google, dict):
        root_google = {}

    model = (
        str(root_google.get("model", "")).strip()
        or _pick_model(root_agent, root_llm, {})
        or DEFAULT_GEMINI_MODEL
    )
    google_timeout = _to_float(
        root_google.get("request_timeout", root_agent.get("request_timeout", 45.0)),
        45.0,
    )

    llm_cfg = cfg.setdefault("llm", {})
    ollama_cfg = cfg.setdefault("ollama", {})
    vision_cfg = cfg.setdefault("vision_llm", {})
    google_cfg = cfg.setdefault("google_ai_studio", {})

    llm_cfg["provider"] = "google_ai_studio"
    llm_cfg["single_model_mode"] = True
    llm_cfg["primary_model"] = model
    llm_cfg["model"] = model
    llm_cfg["clm_fallback_enabled"] = False
    llm_cfg["clm_fallback_model"] = ""
    llm_cfg["fallback_on_missing_model"] = False
    llm_cfg["fallback_on_error"] = False

    vlm_root = require_dict_section(root_cfg, "vlm_bridge")
    vlm_ollama = vlm_root.get("ollama", {}) if isinstance(vlm_root.get("ollama"), dict) else {}
    explicit_endpoint = str(vlm_ollama.get("endpoint", "")).strip()
    ollama_cfg["endpoint"] = _to_vlm_chat_endpoint(
        explicit_endpoint or "http://127.0.0.1:8080/ollama/chat"
    )
    ollama_cfg["model"] = model
    ollama_cfg["timeout"] = _to_float(ollama_cfg.get("timeout", 12.0), 12.0)

    vision_cfg["enabled"] = bool(vision_cfg.get("enabled", True))
    vision_cfg["provider"] = "google_ai_studio"

    google_cfg.update(
        {
            **root_google,
            "model": model,
            "request_timeout": google_timeout,
        }
    )
    cfg["google_ai_studio"] = google_cfg
    cfg["llm"] = llm_cfg
    cfg["ollama"] = ollama_cfg
    cfg["vision_llm"] = vision_cfg
    return cfg


def _enforce_ollama_policy(cfg: Dict[str, Any], root_cfg: Dict[str, Any]) -> Dict[str, Any]:
    root_agent = require_dict_section(root_cfg, "agent")
    root_llm = require_dict_section(root_cfg, "llm")
    root_ollama = require_dict_section(root_cfg, "ollama")

    model = _pick_model(root_agent, root_llm, root_ollama) or _REQUIRED_OLLAMA_MODEL
    if model != _REQUIRED_OLLAMA_MODEL:
        raise ValueError(
            f"Ollama profile requires model '{_REQUIRED_OLLAMA_MODEL}', got '{model}'"
        )

    base_url = _normalize_ollama_base_url(
        root_agent.get("ollama_base_url")
        or root_llm.get("base_url")
        or root_ollama.get("base_url")
        or os.getenv("AGENT_OLLAMA_BASE_URL")
        or "http://127.0.0.1:11434"
    )
    if not base_url:
        raise ValueError("agent.ollama_base_url is required")

    llm_cfg = cfg.setdefault("llm", {})
    ollama_cfg = cfg.setdefault("ollama", {})
    vision_cfg = cfg.setdefault("vision_llm", {})

    llm_cfg["provider"] = "ollama"
    llm_cfg["single_model_mode"] = True
    llm_cfg["primary_model"] = _REQUIRED_OLLAMA_MODEL
    llm_cfg["model"] = _REQUIRED_OLLAMA_MODEL
    llm_cfg["clm_fallback_enabled"] = False
    llm_cfg["clm_fallback_model"] = ""
    llm_cfg["fallback_on_missing_model"] = False
    llm_cfg["fallback_on_error"] = False

    vlm_root = require_dict_section(root_cfg, "vlm_bridge")
    vlm_ollama = vlm_root.get("ollama", {}) if isinstance(vlm_root.get("ollama"), dict) else {}
    explicit_endpoint = str(vlm_ollama.get("endpoint", "")).strip()
    ollama_cfg["endpoint"] = _to_vlm_chat_endpoint(explicit_endpoint or base_url)
    ollama_cfg["model"] = _REQUIRED_OLLAMA_MODEL
    ollama_cfg["timeout"] = _to_float(
        ollama_cfg.get("timeout", root_ollama.get("request_timeout", 12.0)),
        12.0,
    )

    vision_cfg["provider"] = str(vision_cfg.get("provider", "ollama")).strip().lower() or "ollama"
    if vision_cfg.get("base_url") in (None, ""):
        vision_cfg["base_url"] = base_url

    cfg["ollama"] = ollama_cfg
    cfg["llm"] = llm_cfg
    cfg["vision_llm"] = vision_cfg
    return cfg


def _enforce_policy(cfg: Dict[str, Any], root_cfg: Dict[str, Any]) -> Dict[str, Any]:
    root_llm = require_dict_section(root_cfg, "llm")
    provider = str(root_llm.get("provider", "ollama")).strip().lower() or "ollama"
    if provider in _GOOGLE_PROVIDERS:
        return _enforce_google_policy(cfg, root_cfg)
    return _enforce_ollama_policy(cfg, root_cfg)


def load_config(base_dir: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    agent_cfg_path = _resolve_agent_cfg_path(base_dir)
    root_cfg = load_agent_config(agent_cfg_path)
    vlm_cfg = require_dict_section(root_cfg, "vlm_bridge")

    cfg: Dict[str, Any] = deep_merge(DEFAULT_CONFIG, vlm_cfg)
    if overrides:
        cfg = deep_merge(cfg, {k: v for k, v in overrides.items() if v is not None})

    root_google = root_cfg.get("google_ai_studio", {})
    if isinstance(root_google, dict) and root_google:
        cfg["google_ai_studio"] = deep_merge(
            cfg.get("google_ai_studio", {}) if isinstance(cfg.get("google_ai_studio"), dict) else {},
            root_google,
        )

    return _enforce_policy(cfg, root_cfg)
