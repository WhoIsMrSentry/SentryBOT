from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml

_DEFAULT_CFG_PATH = Path(__file__).parent / "config" / "config.yml"


def _deep_update(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = _deep_update(base[k], v)
        else:
            base[k] = v
    return base


def load_config(path: str | os.PathLike | None = None, overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    cfg_path = Path(path) if path else _DEFAULT_CFG_PATH
    if not cfg_path.exists():
        cfg_path = _DEFAULT_CFG_PATH

    with open(cfg_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    env: Dict[str, Any] = {}
    base = os.getenv("ESP_LINK_BASE_URL") or os.getenv("SENTRYBOT_ESP_BASE_URL")
    if base:
        env["base_url"] = str(base).strip()

    out = _deep_update(data, env)

    try:
        from modules.config_center.agent_yaml_loader import load_agent_config

        root = load_agent_config()
        link_cfg = root.get("esp_link")
        if isinstance(link_cfg, dict):
            out = _deep_update(out, link_cfg)
    except FileNotFoundError:
        pass
    except Exception:
        pass
    if overrides:
        out = _deep_update(out, dict(overrides))
    return out
