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
    # If the selected provider requires secrets from a .env file, load them
    provider = str(cfg.get("llm", {}).get("provider", "ollama")).strip().lower() or "ollama"
    if provider in {"google", "google_ai_studio", "gemini"}:
        # Look for an .env file inside the modules/ollama package directory
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        try:
            _load_env_file(env_path)
        except Exception:
            # Don't fail configuration load if env parsing has issues
            pass
    return cfg


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
