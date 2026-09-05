from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional


def _normalize(text: str) -> List[str]:
    return [t for t in text.lower().strip().split() if t]


@dataclass
class WakewordConfig:
    words: List[str]
    trigger_on_partial: bool
    min_confidence: float
    cooldown_sec: float


class WakewordDetector:
    def __init__(self, cfg: dict):
        words = [w for w in (cfg.get("words") or []) if isinstance(w, str) and w.strip()]
        self.cfg = WakewordConfig(
            words=words,
            trigger_on_partial=bool(cfg.get("trigger_on_partial", True)),
            min_confidence=float(cfg.get("min_confidence", 0.0)),
            cooldown_sec=float(cfg.get("cooldown_sec", 2.0)),
        )
        self._word_tokens = [
            _normalize(w) for w in self.cfg.words if _normalize(w)
        ]

    def match(self, text: str) -> Optional[str]:
        if not text:
            return None
        tokens = _normalize(text)
        if not tokens:
            return None
        for idx, w_tokens in enumerate(self._word_tokens):
            if not w_tokens:
                continue
            for i in range(0, len(tokens) - len(w_tokens) + 1):
                if tokens[i:i + len(w_tokens)] == w_tokens:
                    return self.cfg.words[idx]
        return None
