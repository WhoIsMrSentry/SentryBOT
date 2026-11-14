from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from modules.common.config_loader import deep_merge, load_agent_config

_DEFAULT_CFG_PATH = Path(__file__).parent / "config" / "config.yml"


def load_config(path: str | None = None) -> Dict[str, Any]:
    """Load cognitive_memory defaults merged with config/agent.yaml overrides."""
    base_cfg: Dict[str, Any] = {}
    if _DEFAULT_CFG_PATH.exists():
        base_cfg = yaml.safe_load(_DEFAULT_CFG_PATH.read_text(encoding="utf-8")) or {}

    if path:
        explicit = Path(path)
        if explicit.exists():
            override = yaml.safe_load(explicit.read_text(encoding="utf-8")) or {}
            return deep_merge(base_cfg, override)

    try:
        agent_cfg = load_agent_config() or {}
        if isinstance(agent_cfg.get("social_db"), dict):
            base_cfg = deep_merge(base_cfg, agent_cfg["social_db"])
        if isinstance(agent_cfg.get("cognitive_memory"), dict):
            base_cfg = deep_merge(base_cfg, agent_cfg["cognitive_memory"])
    except Exception:
        pass
    return base_cfg
