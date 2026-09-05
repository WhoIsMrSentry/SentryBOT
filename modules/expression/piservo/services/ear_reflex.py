"""Acoustic Ear Reflex Engine (İşitsel Kulak Refleksi).

Canlı bir hayvan veya insansı robot gibi, ortamda ani bir ses veya yönlü konuşma (DOA)
algılandığında robot tüm kafasını çevirmeden önce milisaniyeler içinde ses gelen
yöndeki kulağını dikleştirir ve seğirtir (ear twitch).
"""

from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Tuple, Optional

@dataclass
class EarAngles:
    left: float
    right: float

class EarReflexEngine:
    def __init__(self, neutral_left: float = 90.0, neutral_right: float = 90.0) -> None:
        self.neutral_left = neutral_left
        self.neutral_right = neutral_right
        self._last_twitch_ts = 0.0
        self._twitch_cooldown_s = 0.4

    def compute_reflex(self, doa_angle_deg: float, energy: float = 1.0) -> EarAngles:
        """
        doa_angle_deg: -90 (tam sol) ile +90 (tam sağ) arası ses açısı.
        energy: Sesin ani şiddeti (0.0 - 1.0).
        """
        now = time.time()
        if now - self._last_twitch_ts < self._twitch_cooldown_s:
            return EarAngles(self.neutral_left, self.neutral_right)

        self._last_twitch_ts = now
        strength = max(0.2, min(1.0, float(energy)))

        # Sol taraftan gelen ses: Sol kulak dikleşir (60 deg), sağ kulak hafif gevşer
        if doa_angle_deg < -20:
            l_deg = max(50.0, self.neutral_left - (35.0 * strength))
            r_deg = min(100.0, self.neutral_right + (10.0 * strength))
            return EarAngles(left=round(l_deg, 1), right=round(r_deg, 1))

        # Sağ taraftan gelen ses: Sağ kulak dikleşir (60 deg), sol kulak hafif gevşer
        elif doa_angle_deg > 20:
            r_deg = max(50.0, self.neutral_right - (35.0 * strength))
            l_deg = min(100.0, self.neutral_left + (10.0 * strength))
            return EarAngles(left=round(l_deg, 1), right=round(r_deg, 1))

        # Karşıdan veya ani yüksek ses: İki kulak birden irkilip dikleşir
        else:
            perk = max(55.0, self.neutral_left - (30.0 * strength))
            return EarAngles(left=round(perk, 1), right=round(perk, 1))

    def compute_vigilance(self) -> Tuple[float, float]:
        """Uyanık / dikkatli dinleme modu pozu."""
        return (65.0, 65.0)

    def compute_relax(self) -> Tuple[float, float]:
        """Rahatlama / sakin mod pozu."""
        return (self.neutral_left, self.neutral_right)
