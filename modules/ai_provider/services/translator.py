from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from modules.common.translator import HybridTranslator, HybridTranslatorConfig

from .clients import LLMClientProtocol

logger = logging.getLogger("ollama.translator")

TranslatorConfig = HybridTranslatorConfig


class OllamaTranslator:
    """Compatibility facade delegating translation to shared HybridTranslator."""

    BRIDGE_LANG = "en"

    def __init__(self, client: Optional[LLMClientProtocol], cfg: Optional[Dict[str, Any]] = None) -> None:
        raw = dict(cfg or {}) if isinstance(cfg, dict) else {}
        if "mode" not in raw and "backend" not in raw:
            raw["mode"] = "ollama" if client is not None else "online_first"
        self.client = client
        self._hybrid = HybridTranslator(raw, ollama_client=client)
        self.BRIDGE_LANG = self._hybrid.BRIDGE_LANG
        # Share config object directly so runtime mutations (e.g. cfg.enabled = True) take effect.
        self.cfg = self._hybrid.cfg

    @staticmethod
    def normalize_lang(lang: Optional[str], fallback: str = "en") -> str:
        return HybridTranslator.normalize_lang(lang, fallback=fallback)

    def detect_language(self, text: str) -> str:
        return self._hybrid.detect_language(text)

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        return self._hybrid.translate(text, source_lang, target_lang)

    def translate_with_meta(self, text: str, source_lang: str, target_lang: str) -> tuple[str, str]:
        return self._hybrid.translate_with_meta(text, source_lang, target_lang)

    def to_bridge(self, text: str, source_lang: Optional[str]) -> str:
        return self._hybrid.to_bridge(text, source_lang)

    def from_bridge(self, text: str, target_lang: Optional[str]) -> str:
        return self._hybrid.from_bridge(text, target_lang)

    def status(self) -> Dict[str, Any]:
        return self._hybrid.status()
