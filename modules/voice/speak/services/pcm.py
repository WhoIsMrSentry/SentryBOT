from __future__ import annotations
from dataclasses import dataclass


@dataclass
class PCM:
    """Basit PCM veri taşıyıcısı.

    data: numpy ndarray (float32 veya int16)
    samplerate: int
    channels: int
    """
    data: any  # numpy.ndarray
    samplerate: int
    channels: int
