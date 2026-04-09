from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict

import yaml

_MODULE_DIR = Path(__file__).parent
_DEFAULT_CFG_PATH = _MODULE_DIR / "config" / "config.yml"
_DEFAULT_DOTENV_PATHS = (
    _MODULE_DIR / ".env",
    _MODULE_DIR.parent / "ollama" / ".env",
    _MODULE_DIR.parent.parent / ".env",
)


def _deep_update(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = _deep_update(base[k], v)
        else:
            base[k] = v
    return base


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _first_env(*keys: str) -> str:
    for key in keys:
        value = os.getenv(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _safe_float(value: str, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def load_config(path: str | os.PathLike | None = None) -> Dict[str, Any]:
    for dotenv_path in _DEFAULT_DOTENV_PATHS:
        _load_dotenv(dotenv_path)

    cfg_path = Path(path) if path else _DEFAULT_CFG_PATH
    if not cfg_path.exists():
        cfg_path = _DEFAULT_CFG_PATH
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    # Env overrides
    env: Dict[str, Any] = {}
    model = _first_env("AGENT_MODEL", "AGENT_OLLAMA_MODEL", "OLLAMA_MODEL")
    if model:
        env.setdefault("agent", {})["model"] = model
        env.setdefault("llm", {})["model"] = model

    cooldown = _first_env("AGENT_COOLDOWN_S")
    if cooldown:
        env.setdefault("agent", {})["cooldown_s"] = _safe_float(cooldown, 1.0)

    ollama_base_url = _first_env("AGENT_OLLAMA_BASE_URL", "OLLAMA_BASE_URL", "OLLAMA_HOST")
    if ollama_base_url:
        env.setdefault("agent", {})["ollama_base_url"] = ollama_base_url
        env.setdefault("llm", {})["base_url"] = ollama_base_url
        env.setdefault("llm", {})["provider"] = "ollama"

    return _deep_update(data, env)
