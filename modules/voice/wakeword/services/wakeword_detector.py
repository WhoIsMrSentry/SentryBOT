from __future__ import annotations

from dataclasses import dataclass
from typing import List


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
