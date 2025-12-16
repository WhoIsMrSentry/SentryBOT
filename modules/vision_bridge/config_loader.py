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
        "processing_mode": "local",  # local | remote
        "blind_mode": {"enabled": False, "interval_seconds": 5.0},
        "confidence_threshold": 0.5,
    },
    "remote": {
        "auth_token": "changeme",  # Override in deployment
        "accept_results": True,
    },
    "ollama": {
        "endpoint": "http://localhost:11434/api/generate",
        "model": "llama3",
    },
    "speak": {
        "endpoint": "http://localhost:8083/speak/say",
    },
    "actions": {
        "endpoint": "http://localhost:8100/autonomy/apply_actions",
        "default_apply": False,
        "timeout": 1.5,
    },
}

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
                cfg.update(data)
            break
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if v is not None})
    return cfg
