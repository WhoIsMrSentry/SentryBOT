from __future__ import annotations

import io
import logging
import threading
import time
import weakref
from dataclasses import dataclass
from typing import Dict, Optional

from .pcm import PCM

_ACTIVE_PLAYERS: "weakref.WeakSet[AudioPlayer]" = weakref.WeakSet()
_ACTIVE_LOCK = threading.Lock()
_play_stop = threading.Event()
_global_stop_epoch: int = 0

try:
    import sounddevice as sd
    import soundfile as sf  # noqa: F401 -- used lazily in play_wav_bytes
except Exception:
    sd = None  # type: ignore
    sf = None  # type: ignore

logger = logging.getLogger("speak.player")


class _StopPlaybackDescriptor:
    """Allow stop_playback() on both AudioPlayer instances and the AudioPlayer class."""

    def __get__(self, instance: Optional["AudioPlayer"], owner: type["AudioPlayer"]):
        if instance is not None:
            return instance._stop_instance
        return owner._stop_all


@dataclass
class OutputConfig:
    device: Optional[str] = None
    samplerate: int = 22050
    channels: int = 1
    dtype: str = "float32"


class AudioPlayer:
    def __init__(self, cfg: Dict):
        self.cfg = OutputConfig(
            device=cfg.get("device"),
            samplerate=int(cfg.get("samplerate", 22050)),
            channels=int(cfg.get("channels", 1)),
            dtype=str(cfg.get("dtype", "float32")),
        )
        self._play_lock = threading.Lock()
        self._play_stop = threading.Event()
        with _ACTIVE_LOCK:
            _ACTIVE_PLAYERS.add(self)

    def _stop_instance(self) -> None:
        """Stop playback immediately without blocking on _play_lock."""
        global _global_stop_epoch
        with _ACTIVE_LOCK:
            _global_stop_epoch += 1
            self._play_stop.set()
            _play_stop.set()
        if sd is not None:
            try:
                sd.stop()
            except Exception as exc:
                logger.debug("stop_playback: %s", exc)

    @classmethod
    def _stop_all(cls) -> None:
        global _global_stop_epoch
        with _ACTIVE_LOCK:
            _global_stop_epoch += 1
            _play_stop.set()
            players = list(_ACTIVE_PLAYERS)
        for p in players:
            p._play_stop.set()
        if sd is not None:
            try:
                sd.stop()
            except Exception as exc:
                logger.debug("stop_playback: %s", exc)

    stop_playback = _StopPlaybackDescriptor()

    @property
    def stop_epoch(self) -> int:
        with _ACTIVE_LOCK:
            return _global_stop_epoch

    def clear_stop(self) -> None:
        """Clear both instance and module-global stop flags for a fresh utterance."""
        with _ACTIVE_LOCK:
            self._play_stop.clear()
            _play_stop.clear()

    @property
    def is_stopped(self) -> bool:
        return self._play_stop.is_set() or _play_stop.is_set()

    def _ensure_backends(self) -> None:
        if sd is None:
            raise RuntimeError("sounddevice not available. Install with 'pip install sounddevice'.")

    def play_blocking(self, pcm: PCM) -> float:
        """Play PCM float32 audio and wait interruptibly via Event.wait."""
        self._ensure_backends()
        import numpy as np

        data = pcm.data
        if data.dtype != np.float32:
            data = data.astype(np.float32)

        in_sr = int(pcm.samplerate or self.cfg.samplerate or 22050)
        out_sr = int(self.cfg.samplerate or in_sr)
        if out_sr > 0 and in_sr > 0 and in_sr != out_sr and data.size > 0:
            new_len = max(1, int(round(data.shape[0] * (out_sr / float(in_sr)))))
            x_old = np.linspace(0.0, 1.0, data.shape[0])
            x_new = np.linspace(0.0, 1.0, new_len)
            if data.ndim == 1:
                data = np.interp(x_new, x_old, data).astype(np.float32)
            else:
                cols = [np.interp(x_new, x_old, data[:, c]) for c in range(data.shape[1])]
                data = np.stack(cols, axis=1).astype(np.float32)
            play_sr = out_sr
        else:
            play_sr = in_sr

        if data.ndim == 1 and self.cfg.channels == 2:
            data = np.stack([data, data], axis=1)
        elif data.ndim == 2 and data.shape[1] != self.cfg.channels:
            if self.cfg.channels == 1:
                data = data.mean(axis=1).astype(np.float32)
            else:
                data = np.stack([data[:, 0]] * self.cfg.channels, axis=1).astype(np.float32)

        self.clear_stop()
        dur_sec = len(data) / max(1, play_sr)

        with self._play_lock:
            sd.play(data, samplerate=play_sr, device=self.cfg.device, blocking=False)
            started = time.monotonic()
            end_time = started + dur_sec
            while True:
                remaining = end_time - time.monotonic()
                if remaining <= 0:
                    break
                if self._play_stop.wait(timeout=min(0.05, remaining)) or _play_stop.is_set():
                    try:
                        sd.stop()
                    except Exception:
                        pass
                    break
            if not self.is_stopped:
                try:
                    sd.stop()
                except Exception:
                    pass

        dur = max(0.0, time.monotonic() - started)
        if self.is_stopped:
            logger.info("Playback interrupted after %.2fs", dur)
        else:
            logger.info("Played audio: %.2fs @ %d Hz via %s", dur, play_sr, self.cfg.device or "default")
        return dur

    def play_wav_bytes(self, payload: bytes) -> float:
        """Read WAV bytes and play blocking."""
        import soundfile as sf

        f = io.BytesIO(payload)
        data, sr = sf.read(f, dtype="float32")
        ch = 1 if data.ndim == 1 else data.shape[1]
        pcm = PCM(data=data, samplerate=sr, channels=ch)
        return self.play_blocking(pcm)
