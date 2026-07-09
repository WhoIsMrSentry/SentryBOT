from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .clients import LLMClientProtocol

try:
    from langdetect import detect as _detect_lang  # type: ignore
    from langdetect import DetectorFactory  # type: ignore
    DetectorFactory.seed = 0
except Exception:
    _detect_lang = None  # type: ignore

logger = logging.getLogger("ollama.translator")

_TR_CHARS = set("çğıöşüÇĞİÖŞÜ")
_TR_HINT_WORDS = frozenset({
    "merhaba", "naber", "evet", "hayir", "hayır", "tamam", "günaydın", "gunaydin",
    "nasilsin", "nasılsın", "iyi", "degil", "değil", "lutfen", "lütfen",
})


@dataclass
class TranslatorConfig:
    enabled: bool = True
    default_source_lang: str = "tr"
    model: Optional[str] = None
    cache_size: int = 128


class OllamaTranslator:
    """Small translation facade that uses Ollama chat with strict prompts."""

    BRIDGE_LANG = "en"

    def __init__(self, client: LLMClientProtocol, cfg: Dict):
        self.client = client
        self.cfg = TranslatorConfig(
            enabled=bool(cfg.get("enabled", True)),
            default_source_lang=str(cfg.get("default_source_lang", "tr") or "tr"),
            model=str(cfg.get("model", "")).strip() or None,
            cache_size=max(0, int(cfg.get("cache_size", 128))),
        )
        self._cache: "OrderedDict[Tuple[str, str, str], str]" = OrderedDict()
        self._detect_cache: "OrderedDict[str, str]" = OrderedDict()

    @staticmethod
    def normalize_lang(lang: Optional[str], fallback: str = "en") -> str:
        raw = (lang or "").strip().lower().replace("_", "-")
        if not raw:
            return fallback
        if "-" in raw:
            raw = raw.split("-", 1)[0]
        return raw

    def _cache_get(self, key: Tuple[str, str, str]) -> Optional[str]:
        if not self.cfg.cache_size:
            return None
        value = self._cache.get(key)
        if value is not None:
            self._cache.move_to_end(key)
        return value

    def _cache_put(self, key: Tuple[str, str, str], value: str) -> None:
        if not self.cfg.cache_size:
            return
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > self.cfg.cache_size:
            self._cache.popitem(last=False)

    def _detect_cache_get(self, text: str) -> Optional[str]:
        if not self.cfg.cache_size:
            return None
        value = self._detect_cache.get(text)
        if value is not None:
            self._detect_cache.move_to_end(text)
        return value

    def _detect_cache_put(self, text: str, lang: str) -> None:
        if not self.cfg.cache_size:
            return
        self._detect_cache[text] = lang
        self._detect_cache.move_to_end(text)
        while len(self._detect_cache) > self.cfg.cache_size:
            self._detect_cache.popitem(last=False)

    def detect_language(self, text: str) -> str:
        value = str(text or "").strip()
        if not value:
            return self.cfg.default_source_lang

        cached = self._detect_cache_get(value)
        if cached:
            return cached

        lang = self.cfg.default_source_lang
        words = {w.lower() for w in value.split() if w.strip()}
        if any(ch in _TR_CHARS for ch in value) or (words & _TR_HINT_WORDS):
            lang = "tr"
        elif _detect_lang is not None:
            try:
                detected = self.normalize_lang(str(_detect_lang(value)), fallback=lang)
                if detected and detected != "auto":
                    lang = detected
            except Exception as exc:
                logger.debug("langdetect failed, using default source language: %s", exc)

        self._detect_cache_put(value, lang)
        return lang

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        value = str(text or "").strip()
        if not value:
            return ""
        src = self.normalize_lang(source_lang, fallback=self.cfg.default_source_lang)
        tgt = self.normalize_lang(target_lang, fallback=self.BRIDGE_LANG)
        if not self.cfg.enabled or src == tgt:
            return value

        key = (value, src, tgt)
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        # Keep the prompt strict to avoid style drift and preserve semantics.
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a translation engine. "
                    "Return only translated text with no commentary, no markdown, no quotes. "
                    "Preserve intent, entities, and imperative tone."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Translate from {src} to {tgt}.\\n"
                    "If text is already in target language, return it unchanged.\\n"
                    f"Text: {value}"
                ),
            },
        ]

        try:
            resp = self.client.chat(
                messages,
                options={"temperature": 0.0},
                model=self.cfg.model,
            )
            translated = str(resp.get("message", {}).get("content", "")).strip()
            if not translated:
                return value
            self._cache_put(key, translated)
            return translated
        except Exception as exc:
            from modules.config_center.log_redact import redact_secrets

            logger.warning(
                "Translation failed (%s->%s), using original text: %s",
                src,
                tgt,
                redact_secrets(exc),
            )
            return value

    def to_bridge(self, text: str, source_lang: Optional[str]) -> str:
        src = self.normalize_lang(source_lang, fallback=self.cfg.default_source_lang)
        if src == "auto":
            src = self.detect_language(text)
        return self.translate(text, src, self.BRIDGE_LANG)

    def from_bridge(self, text: str, target_lang: Optional[str]) -> str:
        tgt = self.normalize_lang(target_lang, fallback=self.cfg.default_source_lang)
        return self.translate(text, self.BRIDGE_LANG, tgt)
