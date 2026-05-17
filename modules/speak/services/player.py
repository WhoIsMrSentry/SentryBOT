from __future__ import annotations
import io
import logging
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional
from .pcm import PCM

_play_lock = threading.Lock()
_play_stop = threading.Event()

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

    @staticmethod
    def stop_playback() -> None:
        """Stop any in-progress speaker output (barge-in / wakeword)."""
        _play_stop.set()
        if sd is None:
            return
        try:
            with _play_lock:
                sd.stop()
        except Exception as exc:
            logger.debug("stop_playback: %s", exc)

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

        _play_stop.clear()
        started = time.monotonic()
        with _play_lock:
            sd.play(data, samplerate=pcm.samplerate, device=self.cfg.device, blocking=False)
            while True:
                if _play_stop.is_set():
                    sd.stop()
                    break
                try:
                    sd.wait(timeout=0.05)
                    sd.stop()
                    break
                except Exception:
                    sd.stop()
                    break
        dur = max(0.0, time.monotonic() - started)
        if _play_stop.is_set():
            logger.info("Playback interrupted after %.2fs", dur)
        else:
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
