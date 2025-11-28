from __future__ import annotations
import os
from typing import Any, Dict, Optional
try:
    import yaml  # type: ignore
except Exception:
    yaml = None

DEFAULT_CONFIG: Dict[str, Any] = {
    "server": {"host": "0.0.0.0", "port": 8080},
    "include": {
    "arduino": True,
    "vision_bridge": True,
    "neopixel": True,
    "interactions": True,
    "speak": True,
    "speech": True,
    "ollama": True,
    "wiki_rag": True,
    "camera": True,
    "logs": True,
    "animate": True,
    "piservo": True,
    "ota": True,
    "mutagen": True,
    },
}

def load_config(base_dir: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg: Dict[str, Any] = dict(DEFAULT_CONFIG)
    candidates = []
    # Highest priority: explicit env var path
    env_path = os.getenv("GATEWAY_CONFIG")
    if env_path and os.path.exists(env_path):
        candidates.append(env_path)
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
        cfg = _deep_update(cfg, overrides)
    return cfg

def _deep_update(base: Dict[str, Any], up: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in up.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_update(out[k], v)  # type: ignore
        else:
            out[k] = v
    return out
