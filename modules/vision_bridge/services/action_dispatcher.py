from __future__ import annotations
"""LLM action dispatch helper for Vision Bridge."""

import logging
from typing import Any, Dict, List

import requests

try:  # pragma: no cover - optional dependency during tests
    from modules.ollama.services.tags import extract_llm_tags  # type: ignore
except Exception:  # pragma: no cover
    extract_llm_tags = None  # type: ignore

logger = logging.getLogger("vision_bridge.actions")


class VisionActionDispatcher:
    """Parses semantic descriptions and forwards action tags to Autonomy."""

    def __init__(self, endpoint: str, timeout: float = 1.5, enabled: bool = False) -> None:
        self.endpoint = (endpoint or "").strip()
        self.timeout = timeout
        self.enabled = enabled and bool(self.endpoint)

    def emit_scene(self, semantic_describer, results: List[Dict[str, Any]]) -> None:
        if not self.enabled or not results or semantic_describer is None:
            return
        try:
            prompt = semantic_describer.describe(results)
        except Exception as exc:
            logger.debug("Semantic describe failed: %s", exc)
            return
        self._emit_from_text(prompt)

    def _emit_from_text(self, prompt: str) -> None:
        if not self.enabled or not prompt or extract_llm_tags is None:
            return
        cleaned, parsed = extract_llm_tags(prompt)
        if not parsed:
            return
        payload = {
            "text": cleaned,
            "raw": prompt,
            "actions": parsed,
            "speak": False,
        }
        try:
            requests.post(self.endpoint, json=payload, timeout=self.timeout)
        except Exception as exc:  # pragma: no cover - network
            logger.debug("Vision action dispatch failed: %s", exc)


__all__ = ["VisionActionDispatcher"]
