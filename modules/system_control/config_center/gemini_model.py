"""Backward-compatibility shim for default Gemini model id.

Delegates directly to modules.common.config_loader as the single source of truth.
"""
from __future__ import annotations

from modules.common.config_loader import DEFAULT_GEMINI_MODEL

__all__ = ["DEFAULT_GEMINI_MODEL"]
