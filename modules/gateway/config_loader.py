from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from modules.common.config_loader import _deep_update

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

logger = logging.getLogger("gateway.config_loader")

DEFAULT_CONFIG: Dict[str, Any] = {
    "server": {"host": "0.0.0.0", "port": 8080},
    "include": {
        "arduino": True,
        "vlm_bridge": True,
        "neopixel": True,
        "interactions": True,
        "speak": True,
        "speech": True,
        "ollama": True,
        "camera": True,
        "logs": True,
        "animate": True,
        "piservo": True,
    },
}


def _resolve_candidate(base_dir: Optional[str]) -> Optional[Path]:
    if base_dir:
        explicit = Path(base_dir)
        if explicit.is_file():
            return explicit
        dir_cfg = explicit / "config" / "config.yml"
        if dir_cfg.is_file():
            return dir_cfg
        logger.warning("explicit gateway config path not found: %s", base_dir)

    env_path = str(os.getenv("GATEWAY_CONFIG", "") or "").strip()
    if env_path:
        env_file = Path(env_path)
        if env_file.is_file():
            return env_file

    default_file = Path(__file__).resolve().parent / "config" / "config.yml"
    return default_file if default_file.is_file() else None


def load_config(base_dir: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg: Dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)
    path = _resolve_candidate(base_dir)
    if path is not None and yaml is not None:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if isinstance(data, dict):
            cfg = _deep_update(cfg, data)
    if overrides:
        cfg = _deep_update(cfg, overrides)
    return cfg

