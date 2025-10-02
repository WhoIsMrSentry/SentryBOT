from __future__ import annotations
import os
from typing import Any, Dict
try:
    import yaml  # type: ignore
except Exception:
    yaml = None

DEFAULT_CFG: Dict[str, Any] = {
    "server": {"host": "0.0.0.0", "port": 8098},
    "mutagen": {
        "enabled": True,
        "pairs": [
            # örnek: ana bilgisayardaki kodları robota senkronla
            {"name": "repo", "alpha": "..", "beta": "/home/pi/SentryBOT", "mode": "two-way-resolved"}
        ],
        "opts": {
            "sync_mode": "two-way-resolved",
            "ignore": [".git", "__pycache__", "*.pyc", "logs/*"],
            "maxProblems": 128
        }
    }
}


def load_config(config_path: str | None = None) -> Dict[str, Any]:
    path = config_path or os.environ.get("MUTAGEN_CFG", "modules/mutagen/config/config.yml")
    data: Dict[str, Any] = {}
    if path and os.path.exists(path) and yaml is not None:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    cfg: Dict[str, Any] = DEFAULT_CFG.copy()
    for k, v in (data or {}).items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg
