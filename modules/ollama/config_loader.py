from __future__ import annotations
import os
from typing import Any, Dict
import yaml

DEFAULT_CFG = {
    "server": {"host": "0.0.0.0", "port": 8099},
    "ollama": {"base_url": "http://localhost:11434", "model": "llama3.2:3b", "request_timeout": 60.0},
    "persona": {"default": "glados", "dir": "modules/ollama/config/personalities"},
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
    return cfg
