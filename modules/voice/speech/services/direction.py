from __future__ import annotations
import math
import numpy as np
from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass
class ArrayGeometry:
    mic_distance_m: float = 0.06  # distance between two mics (meters)
    sound_speed: float = 343.0    # m/s


class DirectionEstimator:
    """Estimate direction of arrival (azimuth) using two mics via GCC-PHAT.

    Expects interleaved int16 stereo frames (L,R,L,R,...) at given sample_rate.
    Returns azimuth in degrees (-90..+90) where + is to the right of mic0.
    """

    def __init__(self, sample_rate: int, geometry: Optional[ArrayGeometry] = None):
        self.fs = sample_rate
        self.geom = geometry or ArrayGeometry()
        self.max_delay = int(self.geom.mic_distance_m / self.geom.sound_speed * self.fs)  # samples

    def _gcc_phat(self, sig, ref, interp=1):
        n = sig.shape[0] + ref.shape[0]
        SIG = np.fft.rfft(sig, n=n)
        REF = np.fft.rfft(ref, n=n)
        R = SIG * np.conj(REF)
        R /= np.abs(R) + 1e-15
        cc = np.fft.irfft(R, n=(n * interp))
        max_shift = int(self.max_delay * interp)
        cc = np.concatenate((cc[-max_shift:], cc[:max_shift+1]))
        shift = np.argmax(np.abs(cc)) - max_shift
        return shift / float(interp)

    def estimate(self, frame_bytes: bytes) -> float:
        data = np.frombuffer(frame_bytes, dtype=np.int16)
        if data.size % 2 != 0:
            data = data[:-1]
        # de-interleave
        L = data[0::2].astype(np.float32)
        R = data[1::2].astype(np.float32)
        delay = self._gcc_phat(L, R)
        # clamp to physical max delay
        delay = max(-self.max_delay, min(self.max_delay, delay))
        tau = delay / self.fs  # seconds
        angle = math.degrees(math.asin(max(-1.0, min(1.0, tau * self.geom.sound_speed / self.geom.mic_distance_m))))
        return float(angle)
