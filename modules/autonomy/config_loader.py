from __future__ import annotations

import os
from typing import Any, Dict, Optional
import yaml


def load_config(
    config_path: Optional[str | Dict[str, Any]] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if isinstance(config_path, dict) and overrides is None:
        overrides = config_path
        config_path = None

    default_path = os.path.join(os.path.dirname(__file__), "config", "config.yml")
    target_path = str(config_path) if (config_path and os.path.exists(str(config_path))) else default_path

    if not os.path.exists(target_path):
        return dict(overrides or {})

    with open(target_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    if overrides and isinstance(overrides, dict):
        config.update(overrides)

    return config
