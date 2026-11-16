"""Legacy compatibility wrapper backed by unified modules.voice.audio_router."""
from __future__ import annotations

import logging
import math
import queue
import struct
import threading
import warnings
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

import numpy as np

from modules.voice.audio_router import (
    AudioCapture as _RouterCapture,
    AudioConfig as _RouterAudioConfig,
    _is_alsa_device_name,
    _portaudio_device,
)

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    try:
        import audioop
    except Exception:
        audioop = None

logger = logging.getLogger("speech.audio")


@dataclass
class AudioConfig:
    device: Any = None
    samplerate: int = 16000
    channels: int = 1
    dtype: str = "int16"
    frame_ms: int = 30
    strict_device: bool = False


class AudioCapture:
    """Compatibility facade delegating hardware capture to modules.voice.audio_router."""

    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.cfg = AudioConfig(
            device=cfg.get("device"),
            samplerate=int(cfg.get("samplerate", 16000)),
            channels=int(cfg.get("channels", 1)),
            dtype=str(cfg.get("dtype", "int16")),
            frame_ms=int(cfg.get("frame_ms", 30)),
            strict_device=bool(cfg.get("strict_device", False)),
        )
        self._lock = threading.Lock()
        self._router_capture: Optional[_RouterCapture] = None
        self._stopped = False

        vu_cfg = cfg.get("vu", {}) if isinstance(cfg.get("vu"), dict) else {}
        self._vu_window_ms = int(vu_cfg.get("window_ms", 90))
        self._vu_noise_floor = float(vu_cfg.get("noise_floor", 120.0))
        self._vu_speech_ceiling = float(vu_cfg.get("speech_ceiling", 6000.0))
        self._vu_left_gain = float(vu_cfg.get("left_gain", 1.0))
        self._vu_right_gain = float(vu_cfg.get("right_gain", 1.0))
        window_frames = self._vu_window_frames()
        self._rms_window: deque[int] = deque(maxlen=window_frames)
        self._rms_left_window: deque[int] = deque(maxlen=window_frames)
        self._rms_right_window: deque[int] = deque(maxlen=window_frames)
        self._rms_lock = threading.Lock()

    def merge_config(self, cfg: Dict[str, Any]) -> None:
        """Apply non-default audio fields without wiping explicit hardware device."""
        if not isinstance(cfg, dict):
            return
        audio = cfg.get("audio", cfg)
        if not isinstance(audio, dict):
            return
        dev = audio.get("device")
        if dev is not None and str(dev).strip().lower() not in {"", "null", "none"}:
            if dev != self.cfg.device and self._router_capture is not None:
                logger.info("audio device changed %s -> %s; restarting capture", self.cfg.device, dev)
                self.stop()
            self.cfg.device = dev
        if audio.get("samplerate") is not None:
            self.cfg.samplerate = int(audio.get("samplerate", self.cfg.samplerate))
        if audio.get("channels") is not None:
            self.cfg.channels = int(audio.get("channels", self.cfg.channels))
        vu_cfg = audio.get("vu") if isinstance(audio.get("vu"), dict) else None
        if vu_cfg is not None:
            with self._rms_lock:
                self._vu_window_ms = int(vu_cfg.get("window_ms", self._vu_window_ms))
                self._vu_noise_floor = float(vu_cfg.get("noise_floor", self._vu_noise_floor))
                self._vu_speech_ceiling = float(vu_cfg.get("speech_ceiling", self._vu_speech_ceiling))
                self._vu_left_gain = float(vu_cfg.get("left_gain", self._vu_left_gain))
                self._vu_right_gain = float(vu_cfg.get("right_gain", self._vu_right_gain))
                window_frames = self._vu_window_frames()
                self._rms_window = deque(self._rms_window, maxlen=window_frames)
                self._rms_left_window = deque(self._rms_left_window, maxlen=window_frames)
                self._rms_right_window = deque(self._rms_right_window, maxlen=window_frames)

    def _vu_window_frames(self) -> int:
        return max(1, int(round(self._vu_window_ms / max(1, self.cfg.frame_ms))))

    def _compute_rms(self, data: bytes) -> int:
        if not data:
            return 0
        try:
            if audioop is not None:
                return audioop.rms(data, 2)
            samples = struct.unpack(f"<{len(data)//2}h", data)
            if not samples:
                return 0
            return int((sum(s * s for s in samples) / len(samples)) ** 0.5)
        except Exception:
            return 0

    def _compute_stereo_rms(self, data: bytes) -> tuple[int, int]:
        if not data or self.cfg.channels < 2:
            mono = self._compute_rms(data)
            return mono, mono
        try:
            samples = struct.unpack(f"<{len(data)//2}h", data)
            if len(samples) < 2:
                mono = self._compute_rms(data)
                return mono, mono
            left_sq = right_sq = 0.0
            n = 0
            for i in range(0, len(samples) - 1, 2):
                left_sq += float(samples[i]) ** 2
                right_sq += float(samples[i + 1]) ** 2
                n += 1
            if n <= 0:
                return 0, 0
            return int((left_sq / n) ** 0.5), int((right_sq / n) ** 0.5)
        except Exception:
            mono = self._compute_rms(data)
            return mono, mono

    def _update_rms(self, data: bytes) -> None:
        if self.cfg.channels >= 2:
            left, right = self._compute_stereo_rms(data)
            with self._rms_lock:
                self._rms_left_window.append(left)
                self._rms_right_window.append(right)
                self._rms_window.append(max(left, right))
        else:
            rms = self._compute_rms(data)
            with self._rms_lock:
                self._rms_window.append(rms)
                self._rms_left_window.append(rms)
                self._rms_right_window.append(rms)

    def _normalized_peak(self, window: deque[int], gain: float = 1.0) -> float:
        if not window:
            return 0.0
        peak = max(window) * max(0.01, float(gain))
        floor = max(1.0, self._vu_noise_floor)
        ceiling = max(floor + 1.0, self._vu_speech_ceiling)
        if peak <= floor:
            return 0.0
        level = (math.log10(peak) - math.log10(floor)) / (math.log10(ceiling) - math.log10(floor))
        return max(0.0, min(1.0, level))

    def get_rms_level(self) -> float:
        with self._rms_lock:
            return self._normalized_peak(self._rms_window, max(self._vu_left_gain, self._vu_right_gain))

    def get_rms_levels(self) -> tuple[float, float]:
        with self._rms_lock:
            return (
                self._normalized_peak(self._rms_left_window, self._vu_left_gain),
                self._normalized_peak(self._rms_right_window, self._vu_right_gain),
            )

    def start(self) -> None:
        with self._lock:
            if self._router_capture is not None:
                return
            self._stopped = False
            frame_size = max(64, int(self.cfg.samplerate * self.cfg.frame_ms / 1000))
            rcfg = _RouterAudioConfig(
                device=str(self.cfg.device or "default"),
                sample_rate=int(self.cfg.samplerate),
                channels=int(self.cfg.channels),
                frame_size=frame_size,
                format=str(self.cfg.dtype),
            )
            cap = _RouterCapture(rcfg)
            if not cap.start():
                raise RuntimeError("No working audio backend could be started.")
            self._router_capture = cap

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            cap = self._router_capture
            self._router_capture = None
        if cap is not None:
            cap.stop()

    def stream(self) -> Iterable[bytes]:
        self.start()
        cap = self._router_capture
        if cap is None:
            return
        chunk_q: "queue.Queue[bytes]" = queue.Queue(maxsize=50)

        class _CompatConsumer:
            def __init__(self, parent: AudioCapture) -> None:
                self._parent = parent

            def on_start(self) -> None:
                pass

            def on_stop(self) -> None:
                self._parent._stopped = True

            def on_audio_frame(self, frame: np.ndarray, timestamp: float) -> None:
                data = frame.tobytes()
                self._parent._update_rms(data)
                try:
                    chunk_q.put_nowait(data)
                except queue.Full:
                    pass

        name = f"compat-{id(chunk_q):x}"
        cap.register_consumer(name, _CompatConsumer(self))
        try:
            while not self._stopped and cap._running:
                try:
                    yield chunk_q.get(timeout=0.1)
                except queue.Empty:
                    continue
        finally:
            cap.unregister_consumer(name)


__all__ = ["AudioCapture", "AudioConfig", "_is_alsa_device_name", "_portaudio_device"]
