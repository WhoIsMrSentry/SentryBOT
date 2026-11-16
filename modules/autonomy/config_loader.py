from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml

from modules.common.bind_host import apply_bind_host
from modules.common.config_loader import deep_merge, load_agent_config

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _merge_idle_tree_behaviors(config: Dict[str, Any]) -> None:
    behaviors = config.get("behaviors")
    if not isinstance(behaviors, dict):
        return
    idle_tree = behaviors.get("idle_tree")
    if not isinstance(idle_tree, dict) or idle_tree.get("actions"):
        return
    raw_path = str(idle_tree.get("path") or "").strip()
    if not raw_path:
        return
    target = Path(raw_path)
    if not target.is_absolute():
        target = _REPO_ROOT / target
    if not target.exists():
        return
    try:
        loaded = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict) and isinstance(loaded.get("actions"), list):
            idle_tree["actions"] = loaded["actions"]
    except Exception:
        pass


def load_config(
    config_path: Optional[str | Dict[str, Any]] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if isinstance(config_path, dict) and overrides is None:
        overrides = config_path
        config_path = None

    default_path = os.path.join(os.path.dirname(__file__), "config", "config.yml")
    explicit_path = bool(config_path and os.path.exists(str(config_path)))
    target_path = str(config_path) if explicit_path else default_path

    if not os.path.exists(target_path):
        return apply_bind_host(dict(overrides or {}), "AUTONOMY_HOST")

    with open(target_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    if not isinstance(config, dict):
        config = {}

    if not explicit_path:
        try:
            agent_cfg = load_agent_config() or {}
            if isinstance(agent_cfg, dict):
                for shared_key in ("llm", "agent", "tri_layer", "autonomy"):
                    section = agent_cfg.get(shared_key)
                    if isinstance(section, dict) and section:
                        existing = config.get(shared_key, {}) if isinstance(config.get(shared_key), dict) else {}
                        config[shared_key] = deep_merge(existing, section)
        except Exception:
            pass

    _merge_idle_tree_behaviors(config)

    if overrides and isinstance(overrides, dict):
        config = deep_merge(config, overrides)

    return apply_bind_host(config, "AUTONOMY_HOST")
