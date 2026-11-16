from __future__ import annotations
from pathlib import Path
from typing import Any, Dict

from modules.common.bind_host import apply_bind_host
from modules.common.config_loader import load_module_config

_DEFAULT_CFG_PATH = Path(__file__).parent / "config" / "config.yml"


def load_config(path: str | None = None) -> Dict[str, Any]:
    cfg = load_module_config(_DEFAULT_CFG_PATH, path)
    return apply_bind_host(cfg, "DIAGNOSTICS_HOST")
