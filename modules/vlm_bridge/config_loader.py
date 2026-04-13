from __future__ import annotations
import os
from typing import Any, Dict, Optional
try:
    import yaml  # type: ignore
except Exception:
    yaml = None

DEFAULT_CONFIG: Dict[str, Any] = {
    "server": {"host": "0.0.0.0", "port": 8099},
    "vision": {
        "processing_mode": "remote",  # local | remote
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
        "primary_model": "gemma-4-26B-A4B",
        "clm_fallback_enabled": True,
        "clm_fallback_model": "qwen3.5:8b",
        "fallback_on_missing_model": True,
        "fallback_on_error": True,
    },
    "ollama": {
        "endpoint": "http://localhost:8080/ollama/chat",
        "model": "gemma-4-26B-A4B",
        "timeout": 5.0,
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


def _deep_update(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_update(dict(base[key]), value)
        else:
            base[key] = value
    return base


def _first_env(*keys: str) -> str:
    for key in keys:
        value = os.getenv(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _to_float(raw: Any, fallback: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


def _to_bool(raw: Any, fallback: bool) -> bool:
    text = str(raw or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return fallback


def _apply_env_overrides(cfg: Dict[str, Any]) -> None:
    llm_cfg = cfg.setdefault("llm", {})
    ollama_cfg = cfg.setdefault("ollama", {})

    provider = _first_env("VLM_PROVIDER", "LLM_PROVIDER")
    if provider:
        llm_cfg["provider"] = provider

    primary_model = _first_env("VLM_PRIMARY_MODEL", "VLM_MODEL", "OLLAMA_MODEL")
    if primary_model:
        llm_cfg["primary_model"] = primary_model

    single_model_mode = _first_env("VLM_SINGLE_MODEL_MODE")
    if single_model_mode:
        llm_cfg["single_model_mode"] = _to_bool(single_model_mode, True)

    fallback_enabled = _first_env("VLM_CLM_FALLBACK_ENABLED", "AGENT_CLM_FALLBACK_ENABLED")
    if fallback_enabled:
        llm_cfg["clm_fallback_enabled"] = _to_bool(fallback_enabled, True)

    fallback_model = _first_env("VLM_CLM_FALLBACK_MODEL", "AGENT_CLM_FALLBACK_MODEL")
    if fallback_model:
        llm_cfg["clm_fallback_model"] = fallback_model

    fallback_on_missing = _first_env("VLM_FALLBACK_ON_MISSING_MODEL")
    if fallback_on_missing:
        llm_cfg["fallback_on_missing_model"] = _to_bool(fallback_on_missing, True)

    fallback_on_error = _first_env("VLM_FALLBACK_ON_ERROR")
    if fallback_on_error:
        llm_cfg["fallback_on_error"] = _to_bool(fallback_on_error, True)

    endpoint = _first_env("VLM_OLLAMA_CHAT_ENDPOINT")
    if endpoint:
        ollama_cfg["endpoint"] = endpoint

    timeout = _first_env("VLM_OLLAMA_TIMEOUT")
    if timeout:
        ollama_cfg["timeout"] = _to_float(timeout, 5.0)


def _apply_single_model_policy(cfg: Dict[str, Any]) -> None:
    llm_cfg = cfg.get("llm", {}) if isinstance(cfg.get("llm", {}), dict) else {}
    ollama_cfg = cfg.get("ollama", {}) if isinstance(cfg.get("ollama", {}), dict) else {}

    if not bool(llm_cfg.get("single_model_mode", True)):
        return

    primary_model = str(llm_cfg.get("primary_model", "")).strip()
    if primary_model:
        ollama_cfg["model"] = primary_model
        cfg["ollama"] = ollama_cfg

def load_config(base_dir: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg: Dict[str, Any] = dict(DEFAULT_CONFIG)
    candidates = []
    if base_dir:
        candidates.append(os.path.join(base_dir, "config", "config.yml"))
    here = os.path.dirname(__file__)
    candidates.append(os.path.join(here, "config", "config.yml"))
    for path in candidates:
        if os.path.exists(path) and yaml is not None:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if isinstance(data, dict):
                cfg = _deep_update(cfg, data)
            break
    if overrides:
        cfg = _deep_update(cfg, {k: v for k, v in overrides.items() if v is not None})

    _apply_env_overrides(cfg)
    _apply_single_model_policy(cfg)
    return cfg
