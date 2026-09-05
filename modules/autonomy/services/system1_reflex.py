"""System 1 Reflex Engine (İki Katmanlı Zihin - Hızlı Beden Dili ve Düşünme Refleksi).

Uzak PC'deki Ollama modelinden derin akıl yürütme beklenirken (System 2) robot
asla donup kalmaz. Milisaniyeler içinde (0-50ms) beden dili mikro-eylemleri üretir:
1. Gözler/Kafa hafif yukarı-sağa düşünme açısına kayar.
2. Kulak hafif seğirir.
3. Uzun süren sorgularda (örn >1.5s) doğal Türkçe mikro-onay ("Hmm...", "Hemen bakıyorum...") seslendirir.
"""

from __future__ import annotations
import random
import time
from typing import Any, Dict, List, Optional, Tuple

THINKING_FILLERS_TR = [
    "Hmm...",
    "Hemen bakıyorum...",
    "Bir düşüneyim...",
    "Hımm, anladım...",
    "Bakalım...",
]

THINKING_FILLERS_EN = [
    "Hmm...",
    "Let me check...",
    "Thinking...",
    "One second...",
]

class System1ReflexEngine:
    def __init__(self, language: str = "tr") -> None:
        self.language = language
        self._last_filler_ts = 0.0
        self._filler_cooldown_s = 15.0  # Sık tekrarı önle

    def get_thinking_body_pose(self) -> Dict[str, Any]:
        """Düşünürken doğal insan/robot duruşu."""
        return {
            "head": {"pan": random.choice([86, 94]), "tilt": 102},  # Hafif yukarı/yana bakış
            "ears": {"left": 80, "right": 70},  # Meraklı kulak açısı
            "eyes": {"mode": "animation", "name": "thinking"},
            "leds": {"mode": "thinking", "color": "#30e3ca"},
        }

    def should_emit_verbal_filler(self, wait_elapsed_s: float) -> bool:
        """Eğer çıkarım 1.2 saniyeden uzun sürdüyse ve bekleme süresi dolmadıysa sesli onay üret."""
        if wait_elapsed_s < 1.2:
            return False
        now = time.time()
        if now - self._last_filler_ts < self._filler_cooldown_s:
            return False
        self._last_filler_ts = now
        return True

    def get_verbal_filler(self) -> str:
        """Rastgele düşünme ara sesi."""
        if self.language.startswith("en"):
            return random.choice(THINKING_FILLERS_EN)
        return random.choice(THINKING_FILLERS_TR)
