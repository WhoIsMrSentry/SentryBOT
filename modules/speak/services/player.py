from __future__ import annotations
import io
import logging
from dataclasses import dataclass
from typing import Dict, Optional
from .pcm import PCM

try:
    import sounddevice as sd
    import soundfile as sf  # for writing/reading wav buffers
except Exception:
    sd = None  # type: ignore
    sf = None  # type: ignore

logger = logging.getLogger("speak.player")


@dataclass
class OutputConfig:
    device: Optional[str] = None  # ALSA device name (I2S/I2C DAC via MAX98357A)
    samplerate: int = 22050
    channels: int = 1
    dtype: str = "float32"  # player expects float32

class AudioPlayer:
    def __init__(self, cfg: Dict):
        self.cfg = OutputConfig(
            device=cfg.get("device"),
            samplerate=int(cfg.get("samplerate", 22050)),
            channels=int(cfg.get("channels", 1)),
            dtype=str(cfg.get("dtype", "float32")),
        )

    def _ensure_backends(self):
        if sd is None:
            raise RuntimeError("sounddevice not available. Install with 'pip install sounddevice'.")

    def play_blocking(self, pcm: PCM) -> float:
        """PCM float32 verisini bloklayıcı şekilde çalar ve süreyi döner."""
        self._ensure_backends()
        import numpy as np

        data = pcm.data
        if data.dtype != np.float32:
            data = data.astype(np.float32)

        # Up/down mix to target channels if needed
        if data.ndim == 1 and self.cfg.channels == 2:
            data = np.stack([data, data], axis=1)
        elif data.ndim == 2 and data.shape[1] != self.cfg.channels:
            if self.cfg.channels == 1:
                data = data.mean(axis=1).astype(np.float32)
            else:
                data = np.stack([data[:, 0]] * self.cfg.channels, axis=1).astype(np.float32)

        sd.play(data, samplerate=pcm.samplerate, device=self.cfg.device, blocking=True)
        sd.stop()
        dur = len(data) / float(pcm.samplerate)
        logger.info("Played audio: %.2fs @ %d Hz via %s", dur, pcm.samplerate, self.cfg.device or "default")
        return dur

    def play_wav_bytes(self, payload: bytes) -> float:
        """WAV (RIFF) byte dizisini okuyup çalar."""
        import io
        import soundfile as sf
        f = io.BytesIO(payload)
        data, sr = sf.read(f, dtype='float32')
        ch = 1 if data.ndim == 1 else data.shape[1]
        pcm = PCM(data=data, samplerate=sr, channels=ch)
        return self.play_blocking(pcm)
