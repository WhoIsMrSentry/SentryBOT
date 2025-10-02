from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict
import yaml

_DEF_CFG_PATH = Path(__file__).parent / "config" / "config.yml"


def load_config(override_path: str | os.PathLike | None = None) -> Dict[str, Any]:
    """Speak modülü için YAML konfigürasyonunu yükler.

    Öncelik: override_path > varsayılan config.yml
    """
    cfg_path = Path(override_path) if override_path else _DEF_CFG_PATH
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data
