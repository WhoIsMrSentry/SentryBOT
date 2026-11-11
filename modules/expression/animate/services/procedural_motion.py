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
from typing import Any, Dict

class ProceduralMotionEngine:
    def __init__(
        self,
        base_pan: float = 90.0,
        base_tilt: float = 90.0,
        breathing_period_s: float = 4.5,
        tilt_amplitude_deg: float = 1.8,
        ear_center_deg: float = 90.0,
        ear_amplitude_deg: float = 1.5,
        saccade_min_s: float = 10.0,
        saccade_max_s: float = 22.0,
    ) -> None:
        self.base_pan = float(base_pan)
        self.base_tilt = float(base_tilt)
        self.period = max(0.2, float(breathing_period_s))
        self.tilt_amplitude_deg = float(tilt_amplitude_deg)
        self.ear_center_deg = float(ear_center_deg)
        self.ear_amplitude_deg = float(ear_amplitude_deg)
        self.saccade_min_s = float(saccade_min_s)
        self.saccade_max_s = max(self.saccade_min_s, float(saccade_max_s))
        self._last_saccade_ts = 0.0
        self._saccade_interval_s = random.uniform(self.saccade_min_s, self.saccade_max_s)
        self._saccade_offset_pan = 0.0

    def compute_motion(self, current_time_s: float | None = None) -> Dict[str, Any]:
        ts = float(current_time_s if current_time_s is not None else time.monotonic())

        # 1. Breathing Sine Wave on tilt axis
        phase = (2.0 * math.pi * ts) / self.period
        breath_tilt = math.sin(phase) * self.tilt_amplitude_deg

        # 2. Periodic micro-saccade on pan axis
        if ts - self._last_saccade_ts > self._saccade_interval_s:
            self._last_saccade_ts = ts
            self._saccade_interval_s = random.uniform(self.saccade_min_s, self.saccade_max_s)
            self._saccade_offset_pan = random.choice([-3.5, -2.0, 0.0, 2.0, 3.5])

        target_pan = round(self.base_pan + self._saccade_offset_pan, 1)
        target_tilt = round(self.base_tilt + breath_tilt, 1)

        # 3. Subtle ear micro-drift around configured center
        ear_drift = math.cos(phase) * self.ear_amplitude_deg
        ear_left = round(self.ear_center_deg + ear_drift, 1)
        ear_right = round(self.ear_center_deg - ear_drift, 1)

        return {
            "pan": target_pan,
            "tilt": target_tilt,
            "ears": {"left": ear_left, "right": ear_right},
            "phase": round(phase % (2.0 * math.pi), 2),
        }
