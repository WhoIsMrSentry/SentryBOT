"""Acoustic Ear Reflex Engine (İşitsel Kulak Refleksi).

Canlı bir hayvan veya insansı robot gibi, ortamda ani bir ses veya yönlü konuşma (DOA)
algılandığında robot tüm kafasını çevirmeden önce milisaniyeler içinde ses gelen
yöndeki kulağını dikleştirir ve seğirtir (ear twitch).
"""

from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class EarAngles:
    left: float
    right: float


class EarReflexEngine:
    def __init__(
        self,
        neutral_left: float = 90.0,
        neutral_right: float = 90.0,
        cooldown_s: float = 0.4,
    ) -> None:
        self.neutral_left = float(neutral_left)
        self.neutral_right = float(neutral_right)
        self._last_twitch_ts: Optional[float] = None
        self._twitch_cooldown_s = max(0.0, float(cooldown_s))

    def compute_reflex(self, doa_angle_deg: float, energy: float = 1.0) -> Optional[EarAngles]:
        """Compute directional ear twitch for a DOA audio event.

        Returns None while inside cooldown so active gestures/twitches are not
        overwritten prematurely with neutral angles.
        """
        now = time.monotonic()
        if self._last_twitch_ts is not None and (now - self._last_twitch_ts) < self._twitch_cooldown_s:
            return None

        self._last_twitch_ts = now
        strength = max(0.2, min(1.0, float(energy)))

        if doa_angle_deg < -20:
            l_deg = max(50.0, self.neutral_left - (35.0 * strength))
            r_deg = min(100.0, self.neutral_right + (10.0 * strength))
            return EarAngles(left=round(l_deg, 1), right=round(r_deg, 1))
        if doa_angle_deg > 20:
            r_deg = max(50.0, self.neutral_right - (35.0 * strength))
            l_deg = min(100.0, self.neutral_left + (10.0 * strength))
            return EarAngles(left=round(l_deg, 1), right=round(r_deg, 1))

        perk_l = max(55.0, self.neutral_left - (30.0 * strength))
        perk_r = max(55.0, self.neutral_right - (30.0 * strength))
        return EarAngles(left=round(perk_l, 1), right=round(perk_r, 1))

    def compute_vigilance(self) -> Tuple[float, float]:
        """Uyanık / dikkatli dinleme modu pozu."""
        return (round(max(50.0, self.neutral_left - 25.0), 1), round(max(50.0, self.neutral_right - 25.0), 1))

    def compute_relax(self) -> Tuple[float, float]:
        """Rahatlama / sakin mod pozu."""
        return (self.neutral_left, self.neutral_right)
