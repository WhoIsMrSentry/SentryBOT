"""Canonical emotion vocabulary resolver for SentryBOT.

Unifies emotion labels across all subsystems (autonomy, oled_faces, neopixel,
speech, expression) into a single canonical taxonomy with rich render hints.

Usage::

    from modules.common.emotion_vocab import get_vocab, Emotion

    vocab = get_vocab()
    vocab.canonical("happy")              # -> Emotion.JOY
    vocab.render("happy")                 # -> EmotionRender(canonical=JOY, ...)
    vocab.render(Emotion.ANGER).neopixel_effect  # -> "PULSE"
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger("common.emotion_vocab")

_CONFIG_PATH = Path(__file__).parent / "config" / "emotions.yml"


class Emotion(str, Enum):
    """Canonical emotion taxonomy — single source of truth."""
    NEUTRAL = "neutral"
    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FURIOUS = "furious"
    FEAR = "fear"
    SURPRISE = "surprise"
    EXCITEMENT = "excitement"
    LOVE = "love"
    DISGUST = "disgust"
    CONFUSION = "confusion"
    WORRIED = "worried"
    BORED = "bored"
    TIRED = "tired"
    CURIOSITY = "curiosity"
    CALM = "calm"
    PRIDE = "pride"
    EMBARRASSMENT = "embarrassment"
    AWE = "awe"
    GLOOMY = "gloomy"
    COOL = "cool"
    DEVIL = "devil"
    KAWAII = "kawaii"
    DEAD = "dead"
    SMOKING = "smoking"
    WIRED = "wired"
    NERVOUS = "nervous"
    DISORIENTED = "disoriented"
    SUSPICIOUS = "suspicious"


@dataclass(frozen=True)
class EmotionRender:
    """Resolved render hints for a canonical emotion across all output modalities."""
    
    canonical: Emotion
    
    # NeoPixel LED strip
    neopixel_effect: str = "BREATHE"
    neopixel_rgb: tuple[int, int, int] = (40, 60, 80)
    neopixel_palette: str = "neutral"
    neopixel_speed: float = 1.0
    neopixel_variants: list[tuple[int, int, int]] = field(default_factory=list)
    
    # OLED Faces (SSD1306)
    oled_animation: str = "normal"
    oled_bitmap: str | None = None
    
    # PiServo (ears)
    ears_position: str = "neutral"
    
    # Head/Body language (servo offsets from center 90,90)
    head_pan_delta: int = 0
    head_tilt_delta: int = 0
    
    # TTS Voice
    voice_tone: str = "neutral"
    voice_pitch_shift: float = 0.0
    voice_speed: float = 1.0
    
    # Semantic properties
    arousal: float = 0.0  # 0.0 - 1.0
    valence: float = 0.0  # -1.0 - 1.0
    intensity: float = 1.0  # 0.0 - 2.0
    
    # Aliases for backward compat
    @property
    def oled(self) -> str:
        return self.oled_animation
    
    @property
    def palette(self) -> str:
        return self.neopixel_palette
    
    @property
    def effect(self) -> str:
        return self.neopixel_effect
    
    @property
    def ears(self) -> str:
        return self.ears_position
    
    @property
    def tone(self) -> str:
        return self.voice_tone
    
    @property
    def rgb(self) -> tuple[int, int, int]:
        return self.neopixel_rgb


class EmotionVocab:
    """Resolver around the canonical emotion config."""
    
    def __init__(
        self,
        default_canonical: Emotion = Emotion.NEUTRAL,
        alias_to_canonical: dict[str, Emotion] | None = None,
        render_hints: dict[Emotion, EmotionRender] | None = None,
    ):
        self.default_canonical = default_canonical
        self._alias_to_canonical: dict[str, Emotion] = alias_to_canonical or {}
        self._render: dict[Emotion, EmotionRender] = render_hints or {}
        
        # Ensure default exists
        if default_canonical not in self._render:
            self._render[default_canonical] = EmotionRender(canonical=default_canonical)
    
    def canonical(self, label: str | Emotion | None) -> Emotion:
        """Map any incoming label to its canonical Emotion."""
        if label is None:
            return self.default_canonical
        if isinstance(label, Emotion):
            return label
        
        key = str(label).strip().lower()
        if not key:
            return self.default_canonical
        
        # Direct match
        try:
            return Emotion(key)
        except ValueError:
            pass
        
        # Alias match
        if key in self._alias_to_canonical:
            return self._alias_to_canonical[key]
        
        # Fuzzy: check if key is prefix of any canonical
        for canon in Emotion:
            if canon.value.startswith(key) or key.startswith(canon.value):
                return canon
        
        logger.debug("Unknown emotion label '%s', defaulting to %s", key, self.default_canonical)
        return self.default_canonical
    
    def render(self, label: str | Emotion | None) -> EmotionRender:
        """Resolve an incoming label to its render hints."""
        canon = self.canonical(label)
        return self._render.get(canon) or self._render.get(self.default_canonical) or EmotionRender(canonical=canon)
    
    def is_known(self, label: str | Emotion | None) -> bool:
        if label is None:
            return False
        if isinstance(label, Emotion):
            return True
        key = str(label).strip().lower()
        return bool(key) and (key in self._alias_to_canonical or 
                               any(k.value == key for k in Emotion))
    
    def all_canonical(self) -> list[Emotion]:
        return list(Emotion)
    
    def get_render_dict(self, label: str | Emotion | None) -> dict[str, Any]:
        """Get render hints as dict for JSON serialization."""
        r = self.render(label)
        return {
            "canonical": r.canonical.value,
            "neopixel": {
                "effect": r.neopixel_effect,
                "rgb": list(r.neopixel_rgb),
                "palette": r.neopixel_palette,
                "speed": r.neopixel_speed,
                "variants": [list(v) for v in r.neopixel_variants],
            },
            "oled": {
                "animation": r.oled_animation,
                "bitmap": r.oled_bitmap,
            },
            "ears": r.ears_position,
            "head": {
                "pan_delta": r.head_pan_delta,
                "tilt_delta": r.head_tilt_delta,
            },
            "voice": {
                "tone": r.voice_tone,
                "pitch_shift": r.voice_pitch_shift,
                "speed": r.voice_speed,
            },
            "semantic": {
                "arousal": r.arousal,
                "valence": r.valence,
                "intensity": r.intensity,
            },
        }


def _coerce_rgb(value: Any, fallback: tuple[int, int, int] = (40, 60, 80)) -> tuple[int, int, int]:
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            return (int(value[0]), int(value[1]), int(value[2]))
        except (TypeError, ValueError):
            return fallback
    return fallback


def _coerce_variants(value: Any) -> list[tuple[int, int, int]]:
    if isinstance(value, list):
        return [_coerce_rgb(v) for v in value if isinstance(v, (list, tuple))]
    return []


def load_vocab(path: Path | None = None) -> EmotionVocab:
    """Build an EmotionVocab from the YAML config (falls back to rich defaults)."""
    cfg_path = Path(path) if path else _CONFIG_PATH
    data: dict[str, Any] = {}
    
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("Emotion config not found at %s, using defaults", cfg_path)
    except Exception as exc:
        logger.warning("Failed to load emotion config: %s", exc)
    
    # Default canonical
    default_canon = Emotion(data.get("default_canonical", "neutral"))
    
    # Aliases
    alias_to_canonical: dict[str, Emotion] = {}
    for canon_str, aliases in (data.get("aliases") or {}).items():
        try:
            canon = Emotion(canon_str.lower())
        except ValueError:
            continue
        alias_to_canonical[canon.value] = canon
        if isinstance(aliases, (list, tuple)):
            for alias in aliases:
                alias_to_canonical[str(alias).strip().lower()] = canon
    
    # Render hints
    render: dict[Emotion, EmotionRender] = {}
    for canon_str, hints in (data.get("render") or {}).items():
        try:
            canon = Emotion(canon_str.lower())
        except ValueError:
            continue
        
        hints = hints if isinstance(hints, dict) else {}
        render[canon] = EmotionRender(
            canonical=canon,
            neopixel_effect=str(hints.get("neopixel_effect", "BREATHE")),
            neopixel_rgb=_coerce_rgb(hints.get("neopixel_rgb")),
            neopixel_palette=str(hints.get("neopixel_palette", "neutral")),
            neopixel_speed=float(hints.get("neopixel_speed", 1.0)),
            neopixel_variants=_coerce_variants(hints.get("neopixel_variants")),
            oled_animation=str(hints.get("oled_animation", "normal")),
            oled_bitmap=hints.get("oled_bitmap"),
            ears_position=str(hints.get("ears_position", "neutral")),
            head_pan_delta=int(hints.get("head_pan_delta", 0)),
            head_tilt_delta=int(hints.get("head_tilt_delta", 0)),
            voice_tone=str(hints.get("voice_tone", "neutral")),
            voice_pitch_shift=float(hints.get("voice_pitch_shift", 0.0)),
            voice_speed=float(hints.get("voice_speed", 1.0)),
            arousal=float(hints.get("arousal", 0.0)),
            valence=float(hints.get("valence", 0.0)),
            intensity=float(hints.get("intensity", 1.0)),
        )
    
    # Ensure default exists
    if default_canon not in render:
        render[default_canon] = EmotionRender(canonical=default_canon)
    
    return EmotionVocab(
        default_canonical=default_canon,
        alias_to_canonical=alias_to_canonical,
        render_hints=render,
    )


_vocab_lock = threading.Lock()
_vocab_singleton: EmotionVocab | None = None


def get_vocab() -> EmotionVocab:
    """Process-wide cached vocabulary."""
    global _vocab_singleton
    if _vocab_singleton is None:
        with _vocab_lock:
            if _vocab_singleton is None:
                _vocab_singleton = load_vocab()
    return _vocab_singleton


def canonical_emotion(label: str | Emotion | None) -> Emotion:
    return get_vocab().canonical(label)


def emotion_render(label: str | Emotion | None) -> EmotionRender:
    return get_vocab().render(label)


def get_emotion_render_dict(label: str | Emotion | None) -> dict[str, Any]:
    return get_vocab().get_render_dict(label)


__all__ = [
    "Emotion",
    "EmotionRender",
    "EmotionVocab",
    "load_vocab",
    "get_vocab",
    "canonical_emotion",
    "emotion_render",
    "get_emotion_render_dict",
]