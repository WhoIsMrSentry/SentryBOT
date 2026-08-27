"""Backward-compatibility shim for agent configuration loading.

Delegates directly to modules.common.config_loader as the single source of truth.
"""
from __future__ import annotations

from modules.common.config_loader import (
    deep_merge,
    load_agent_config,
    resolve_agent_cfg_path,
)

__all__ = [
    "deep_merge",
    "load_agent_config",
    "resolve_agent_cfg_path",
]
