"""Backward-compatibility shim for Google AI Studio API key resolution.

Delegates directly to modules.common.config_loader as the single source of truth.
"""
from __future__ import annotations

from modules.common.config_loader import (
    _sanitize_google_api_key,
    inject_google_api_key,
    resolve_google_api_key,
)

__all__ = [
    "_sanitize_google_api_key",
    "resolve_google_api_key",
    "inject_google_api_key",
]
