from __future__ import annotations
from pathlib import Path
from typing import Any, Dict

from modules.common.config_loader import load_module_config

_DEFAULT_CFG_PATH = Path(__file__).parent / "config" / "config.yml"


def load_config(path: str | None = None) -> Dict[str, Any]:
    return load_module_config(_DEFAULT_CFG_PATH, path)
