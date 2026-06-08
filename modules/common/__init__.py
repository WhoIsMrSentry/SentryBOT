"""Shared, dependency-light helpers used across SentryBOT modules.

Currently hosts the canonical emotion vocabulary so eyes, LEDs, ears, body
language and TTS tone all agree on a single emotion taxonomy.
"""

from .emotion_vocab import (
    EmotionRender,
    EmotionVocab,
    canonical_emotion,
    emotion_render,
    get_vocab,
    load_vocab,
)

__all__ = [
    "EmotionRender",
    "EmotionVocab",
    "canonical_emotion",
    "emotion_render",
    "get_vocab",
    "load_vocab",
]
