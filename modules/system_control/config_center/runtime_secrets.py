"""Backward-compatibility shim for runtime secrets overlay.

Delegates directly to modules.common.config_loader as the single source of truth.
"""
from __future__ import annotations

from modules.common.config_loader import (
    _ENV_PATHS,
    _ensure_path,
    _repo_root,
    inject_runtime_secrets,
    load_dotenv,
)

__all__ = [
    "_ENV_PATHS",
    "_repo_root",
    "_ensure_path",
    "load_dotenv",
    "inject_runtime_secrets",
]
