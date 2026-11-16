from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Any, Dict

import yaml

from modules.common.config_loader import _deep_update

_DEFAULT_CFG_PATH = Path(__file__).parent / "config" / "config.yml"
logger = logging.getLogger("piservo.config")


def load_config(path: str | os.PathLike | None = None) -> Dict[str, Any]:
    cfg_path = Path(path) if path else Path(os.getenv("PISERVO_CONFIG", _DEFAULT_CFG_PATH))
    if not cfg_path.exists():
        cfg_path = _DEFAULT_CFG_PATH
    with open(cfg_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    env: Dict[str, Any] = {}
    host = os.getenv("PISERVO_HOST")
    port_raw = os.getenv("PISERVO_PORT")
    if host:
        env.setdefault("server", {})["host"] = host
    if port_raw:
        try:
            port_val = int(port_raw)
            if 1 <= port_val <= 65535:
                env.setdefault("server", {})["port"] = port_val
            else:
                logger.warning("Ignoring out-of-range PISERVO_PORT=%r", port_raw)
        except ValueError:
            logger.warning("Ignoring invalid PISERVO_PORT=%r", port_raw)
    return _deep_update(data, env)
