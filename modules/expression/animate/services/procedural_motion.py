"""Procedural Motion Engine (Prosedürel Dinamik Hareket ve Canlılık Nefesi).

Robotun hareketsiz dururken "ölü/donmuş bir plastik" gibi görünmesini engeller.
Doğal bir canlı gibi:
1. Nefes Alma (Breathing Wave): 4-5 saniyelik sinüs dalgası ile kafada hafif dikey (tilt) nefes salınımı.
2. Mikro-Sakkadlar (Micro-Saccades): 10-25 saniyede bir ortamı hafifçe süzen doğal göz/kafa kayması.
3. Kulak Gevşemesi (Ear Micro-Drift): Nefes ritmiyle uyumlu çok hafif mikro kulak hareketi.
"""

from __future__ import annotations
import math
import random
import time
from typing import Any, Dict, Tuple

class ProceduralMotionEngine:
    def __init__(
        self,
        base_pan: float = 90.0,
        base_tilt: float = 90.0,
        breathing_period_s: float = 4.5,
    ) -> None:
        self.base_pan = base_pan
        self.base_tilt = base_tilt
        self.period = breathing_period_s
        self._last_saccade_ts = 0.0
        self._saccade_interval_s = random.uniform(12.0, 20.0)
        self._saccade_offset_pan = 0.0

    def compute_motion(self, current_time_s: float = None) -> Dict[str, Any]:
        ts = float(current_time_s if current_time_s is not None else time.time())

        # 1. Sinüzoidal nefes alma dalgası (Breathing Sine Wave)
        phase = (2.0 * math.pi * ts) / self.period
        # Tilt nefes genliği: +/- 1.8 derece
        breath_tilt = math.sin(phase) * 1.8

        # 2. Rastgele mikro-sakkad (ortam süzme)
        if ts - self._last_saccade_ts > self._saccade_interval_s:
            self._last_saccade_ts = ts
            self._saccade_interval_s = random.uniform(10.0, 22.0)
            # -4 ile +4 derece arası hafif yatay kafa/bakış kayması
            self._saccade_offset_pan = random.choice([-3.5, -2.0, 0.0, 2.0, 3.5])

        target_pan = round(self.base_pan + self._saccade_offset_pan, 1)
        target_tilt = round(self.base_tilt + breath_tilt, 1)

        # 3. Kulak mikro-salınımı (+/- 1.5 derece)
        ear_drift = math.cos(phase) * 1.5
        ear_left = round(90.0 + ear_drift, 1)
        ear_right = round(90.0 - ear_drift, 1)

        return {
            "pan": target_pan,
            "tilt": target_tilt,
            "ears": {"left": ear_left, "right": ear_right},
            "phase": round(phase % (2.0 * math.pi), 2),
        }
