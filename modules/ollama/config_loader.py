from __future__ import annotations
import os
from typing import Any, Dict
import yaml

DEFAULT_CFG = {
    "server": {"host": "0.0.0.0", "port": 8099},
    "llm": {"provider": "ollama"},
    "ollama": {"base_url": "http://localhost:11435", "model": "llama3.2:3b", "request_timeout": 60.0},
    "google_ai_studio": {
        "api_key": "",
        "model": "gemini-1.5-flash",
        "base_url": "https://generativelanguage.googleapis.com",
        "request_timeout": 60.0,
    },
    "persona": {"default": "sentry", "dir": "modules/ollama/config/personalities"},
}


def load_config(config_path: str | None = None) -> Dict[str, Any]:
    path = config_path or os.environ.get("OLLAMA_CFG", "modules/ollama/config/config.yml")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
    # merge shallow
    cfg = DEFAULT_CFG.copy()
    for k, v in (data or {}).items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v

    env_path = os.path.join(os.path.dirname(__file__), ".env")
    try:
        _load_env_file(env_path)
    except Exception:
        # Don't fail configuration load if env parsing has issues
        pass

    _apply_env_overrides(cfg)
    return cfg


def _first_env(*keys: str) -> str:
    for key in keys:
        value = os.environ.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _to_float(raw: str, fallback: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


def _apply_env_overrides(cfg: Dict[str, Any]) -> None:
    llm_cfg = cfg.setdefault("llm", {})
    ollama_cfg = cfg.setdefault("ollama", {})
    google_cfg = cfg.setdefault("google_ai_studio", {})

    provider = _first_env("LLM_PROVIDER", "OLLAMA_PROVIDER")
    if provider:
        llm_cfg["provider"] = provider

    base_url = _first_env("OLLAMA_BASE_URL", "OLLAMA_HOST")
    if base_url:
        ollama_cfg["base_url"] = base_url

    model = _first_env("OLLAMA_MODEL")
    if model:
        ollama_cfg["model"] = model

    request_timeout = _first_env("OLLAMA_REQUEST_TIMEOUT")
    if request_timeout:
        ollama_cfg["request_timeout"] = _to_float(request_timeout, 60.0)

    google_key = _first_env("GOOGLE_API_KEY")
    if google_key:
        google_cfg["api_key"] = google_key

    google_model = _first_env("GOOGLE_MODEL")
    if google_model:
        google_cfg["model"] = google_model


def _load_env_file(env_path: str) -> None:
    """Load simple KEY=VALUE pairs from a .env file into os.environ.

    Existing environment variables are not overwritten (useful for CI/local overrides).
    Lines beginning with '#' are ignored.
    """
    if not env_path or not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            # strip optional quotes
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            if key:
                os.environ.setdefault(key, val)
