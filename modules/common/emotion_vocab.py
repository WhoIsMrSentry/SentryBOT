"""Canonical emotion vocabulary resolver.

Unifies the historically divergent emotion labels used by autonomy (mood),
oled_faces (events) and neopixel (palettes) into one canonical set with shared
render hints (eyes / LEDs / ears / TTS tone).

Usage::

    from modules.common.emotion_vocab import get_vocab

    vocab = get_vocab()
    vocab.canonical("happy")            # -> "joy"
    vocab.render("happy")               # -> EmotionRender(oled="happy", ...)
    vocab.render("happy").palette       # -> "joy"

The module is intentionally dependency-light (PyYAML only) so any service can
import it without pulling heavy module graphs.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger("common.emotion_vocab")

_CONFIG_PATH = Path(__file__).parent / "config" / "emotions.yml"


@dataclass(frozen=True)
class EmotionRender:
    """Resolved render hints for a canonical emotion."""

    canonical: str
    oled: str = "normal"
    palette: str = "neutral"
    effect: str = "BREATHE"
    ears: str = "neutral"
    tone: str = "neutral"
    rgb: tuple = (40, 60, 80)


@dataclass
class EmotionVocab:
    """Resolver around the canonical emotion config."""

    default_canonical: str = "neutral"
    _alias_to_canonical: Dict[str, str] = field(default_factory=dict)
    _render: Dict[str, EmotionRender] = field(default_factory=dict)

    def canonical(self, label: Optional[str]) -> str:
        """Map any incoming label to its canonical key."""
        key = str(label or "").strip().lower()
        if not key:
            return self.default_canonical
        if key in self._render:
            return key
        return self._alias_to_canonical.get(key, self.default_canonical)

    def render(self, label: Optional[str]) -> EmotionRender:
        """Resolve an incoming label to its render hints."""
        canon = self.canonical(label)
        return self._render.get(canon) or self._render.get(self.default_canonical) or EmotionRender(canon)

    def is_known(self, label: Optional[str]) -> bool:
        key = str(label or "").strip().lower()
        return bool(key) and (key in self._render or key in self._alias_to_canonical)

    def canonical_keys(self) -> List[str]:
        return list(self._render.keys())


def _coerce_rgb(value: Any, fallback: tuple = (40, 60, 80)) -> tuple:
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            return (int(value[0]), int(value[1]), int(value[2]))
        except (TypeError, ValueError):
            return fallback
    return fallback


def load_vocab(path: Optional[Path] = None) -> EmotionVocab:
    """Build an :class:`EmotionVocab` from the YAML config (falls back to defaults)."""
    cfg_path = Path(path) if path else _CONFIG_PATH
    data: Dict[str, Any] = {}
    try:
        with open(cfg_path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except FileNotFoundError:
        logger.warning("emotion config not found at %s, using minimal defaults", cfg_path)
    except Exception as exc:  # malformed yaml should not crash a service
        logger.warning("failed to load emotion config: %s", exc)

    default_canon = str(data.get("default_canonical", "neutral")).lower()

    render: Dict[str, EmotionRender] = {}
    for canon, hints in (data.get("render") or {}).items():
        canon_key = str(canon).strip().lower()
        hints = hints if isinstance(hints, dict) else {}
        render[canon_key] = EmotionRender(
            canonical=canon_key,
            oled=str(hints.get("oled", "normal")),
            palette=str(hints.get("palette", "neutral")),
            effect=str(hints.get("effect", "BREATHE")),
            ears=str(hints.get("ears", "neutral")),
            tone=str(hints.get("tone", "neutral")),
            rgb=_coerce_rgb(hints.get("rgb")),
        )

    alias_to_canonical: Dict[str, str] = {}
    for canon, aliases in (data.get("aliases") or {}).items():
        canon_key = str(canon).strip().lower()
        alias_to_canonical[canon_key] = canon_key
        if isinstance(aliases, (list, tuple)):
            for alias in aliases:
                alias_to_canonical[str(alias).strip().lower()] = canon_key

    if default_canon not in render:
        render[default_canon] = EmotionRender(default_canon)

    return EmotionVocab(
        default_canonical=default_canon,
        _alias_to_canonical=alias_to_canonical,
        _render=render,
    )


_vocab_lock = threading.Lock()
_vocab_singleton: Optional[EmotionVocab] = None


def get_vocab() -> EmotionVocab:
    """Process-wide cached vocabulary."""
    global _vocab_singleton
    if _vocab_singleton is None:
        with _vocab_lock:
            if _vocab_singleton is None:
                _vocab_singleton = load_vocab()
    return _vocab_singleton


def canonical_emotion(label: Optional[str]) -> str:
    return get_vocab().canonical(label)


def emotion_render(label: Optional[str]) -> EmotionRender:
    return get_vocab().render(label)


__all__ = [
    "EmotionRender",
    "EmotionVocab",
    "load_vocab",
    "get_vocab",
    "canonical_emotion",
    "emotion_render",
]
