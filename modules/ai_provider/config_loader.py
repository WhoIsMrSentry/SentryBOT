"""Canonical configuration loader for ``modules/ai_provider``.

Delegates to ``modules.common.config_loader.load_ai_provider_config`` so there is
only one source of truth for ``ollama_service`` / ``ai_provider`` YAML merging.
"""
from __future__ import annotations

from typing import Any, Dict

from modules.common.config_loader import (  # noqa: F401
    _normalize_base_url,
    _pick_model,
    _to_float,
    load_ai_provider_config,
)


def load_config(config_path: str | None = None) -> Dict[str, Any]:
    """Load merged ai_provider / ollama_service configuration from agent.yaml."""
    return load_ai_provider_config(config_path)
