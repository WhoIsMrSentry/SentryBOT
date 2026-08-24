from __future__ import annotations
import logging
import math
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Any

try:
    import audioop
except Exception:
    audioop = None

try:
    import sounddevice as sd
except Exception:
    sd = None
try:
    import alsaaudio
except Exception:
    alsaaudio = None

logger = logging.getLogger("speech.audio")


def _is_alsa_device_name(device: Any) -> bool:
    if device is None:
        return False
    text = str(device).strip().lower()
    if not text or text in {"null", "none", "default"}:
        return False
    if text.isdigit():
        return False
    return text.startswith(("plughw:", "hw:", "alsa:", "surround")) or "," in text


def _portaudio_device(device: Any) -> Any:
    if device is None:
        return None
    if isinstance(device, int):
        return device
    text = str(device).strip()
    if text.isdigit():
        return int(text)
    return device

@dataclass
class AudioConfig:
    device: Any = None
    samplerate: int = 16000
    channels: int = 1
    dtype: str = "int16"
    frame_ms: int = 30
    strict_device: bool = False

class AudioCapture:
    """Singleton audio capture supporting multiple broadcast subscribers."""

    def __init__(self, cfg: Dict):
        self.cfg = AudioConfig(
            device=cfg.get("device"),
            samplerate=int(cfg.get("samplerate", 16000)),
            channels=int(cfg.get("channels", 1)),
            dtype=str(cfg.get("dtype", "int16")),
            frame_ms=int(cfg.get("frame_ms", 30)),
            strict_device=bool(cfg.get("strict_device", False)),
        )
        self._subscribers: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._stream = None
        self._stopped = False
        self._alsa_thread = None
        self._pcm = None

        # RMS level tracking (short sliding window per channel)
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

    def merge_config(self, cfg: Dict) -> None:
        """Apply non-default audio fields from a later module (e.g. wakeword plughw)."""
        if not isinstance(cfg, dict):
            return
        audio = cfg.get("audio", cfg)
        if not isinstance(audio, dict):
            return
        dev = audio.get("device")
        # YAML `null` or empty string must not wipe a device set by wakeword bootstrap.
        if dev is not None and str(dev).strip().lower() not in {"", "null", "none"}:
            new_dev = dev
            if new_dev != self.cfg.device and (self._stream is not None or self._alsa_thread is not None):
                logger.info("audio device changed %s -> %s; restarting capture", self.cfg.device, new_dev)
                self.stop()
            self.cfg.device = new_dev
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
        """Compute RMS level from raw PCM int16 data. Returns 0-32767."""
        if not data:
            return 0
        try:
            if audioop is not None:
                return audioop.rms(data, 2)
            import struct
            samples = struct.unpack(f"<{len(data)//2}h", data)
            if not samples:
                return 0
            sum_sq = sum(s * s for s in samples)
            return int((sum_sq / len(samples)) ** 0.5)
        except Exception:
            return 0

    def _compute_stereo_rms(self, data: bytes) -> tuple[int, int]:
        if not data or self.cfg.channels < 2:
            mono = self._compute_rms(data)
            return mono, mono
        try:
            import struct
            samples = struct.unpack(f"<{len(data)//2}h", data)
            if len(samples) < 2:
                mono = self._compute_rms(data)
                return mono, mono
            left_sq = 0.0
            right_sq = 0.0
            n = 0
            for i in range(0, len(samples) - 1, 2):
                l = float(samples[i])
                r = float(samples[i + 1])
                left_sq += l * l
                right_sq += r * r
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
        """Get normalized RMS level (0.0 - 1.0) over the sliding window."""
        with self._rms_lock:
            return self._normalized_peak(self._rms_window, max(self._vu_left_gain, self._vu_right_gain))

    def get_rms_levels(self) -> tuple[float, float]:
        """Get normalized stereo RMS (left, right) over the short sliding window."""
        with self._rms_lock:
            left = self._normalized_peak(self._rms_left_window, self._vu_left_gain)
            right = self._normalized_peak(self._rms_right_window, self._vu_right_gain)
            return left, right

    def _callback(self, indata, frames, time_info, status):
        if status:
            logger.warning("Audio status: %s", status)
        data = bytes(indata)
        self._update_rms(data)
        with self._lock:
            for q in self._subscribers:
                try:
                    q.put_nowait(data)
                except queue.Full:
                    pass

    def _start_alsa(self, blocksize: int) -> bool:
        if alsaaudio is None:
            return False
        try:
            fmt = alsaaudio.PCM_FORMAT_S16_LE if self.cfg.dtype == "int16" else alsaaudio.PCM_FORMAT_S32_LE
            dev_name = str(self.cfg.device) if self.cfg.device is not None else "default"

            self._pcm = alsaaudio.PCM(
                type=alsaaudio.PCM_CAPTURE,
                device=dev_name,
                channels=self.cfg.channels,
                rate=self.cfg.samplerate,
                format=fmt,
                periodsize=max(64, blocksize),
            )

            def _alsa_reader():
                self._stopped = False
                try:
                    while not self._stopped:
                        pcm = self._pcm
                        if pcm is None:
                            break
                        try:
                            length, data = pcm.read()
                        except Exception:
                            break
                        if length > 0 and data:
                            b_data = bytes(data)
                            self._update_rms(b_data)
                            with self._lock:
                                for q in self._subscribers:
                                    try:
                                        q.put_nowait(b_data)
                                    except queue.Full:
                                        pass
                finally:
                    if self._pcm:
                        try:
                            self._pcm.close()
                        except Exception:
                            pass
                        self._pcm = None

            self._alsa_thread = threading.Thread(target=_alsa_reader, daemon=True)
            self._alsa_thread.start()
            logger.info(
                "Audio capture started (ALSA): %s @ %d Hz, %d ch",
                dev_name,
                self.cfg.samplerate,
                self.cfg.channels,
            )
            return True
        except Exception as exc:
            logger.warning("ALSA capture failed for device %s: %s", self.cfg.device, exc)
            self._pcm = None
            self._alsa_thread = None
            return False

    def _start_portaudio(self, blocksize: int) -> bool:
        if sd is None:
            return False
        devs_to_try = [_portaudio_device(self.cfg.device)]
        if self.cfg.device is not None and not bool(self.cfg.strict_device):
            devs_to_try.append(None)
        for dev in devs_to_try:
            try:
                self._stream = sd.InputStream(
                    device=dev,
                    channels=self.cfg.channels,
                    samplerate=self.cfg.samplerate,
                    dtype=self.cfg.dtype,
                    callback=self._callback,
                    blocksize=blocksize,
                )
                self._stream.start()
                self._stopped = False
                logger.info(
                    "Audio capture started (portaudio): %s @ %d Hz, %d ch",
                    dev if dev is not None else "default",
                    self.cfg.samplerate,
                    self.cfg.channels,
                )
                return True
            except Exception as exc:
                logger.warning("sounddevice attempt failed for device %s: %s", dev, exc)
                self._stream = None
        return False

    def start(self):
        with self._lock:
            if self._stream is not None or self._alsa_thread is not None:
                return

            self._stopped = False
            blocksize = int(self.cfg.samplerate * self.cfg.frame_ms / 1000)

            # ALSA device strings (plughw:0,0) are invalid for PortAudio; use ALSA directly.
            if _is_alsa_device_name(self.cfg.device):
                if self._start_alsa(blocksize):
                    return
            elif self._start_portaudio(blocksize):
                return
            elif self._start_alsa(blocksize):
                return

            raise RuntimeError("No working audio backend could be started.")

    def stop(self):
        with self._lock:
            self._stopped = True
            if self._stream:
                try:
                    self._stream.stop()
                    self._stream.close()
                finally:
                    self._stream = None
            if self._pcm:
                try:
                    self._pcm.close()
                finally:
                    self._pcm = None
            self._alsa_thread = None
            logger.info("Audio capture stopped")

    def stream(self) -> Iterable[bytes]:
        q = queue.Queue(maxsize=50)
        with self._lock:
            self._subscribers.append(q)
        
        try:
            if self._stream is None and self._alsa_thread is None:
                self.start()
            
            while not self._stopped:
                try:
                    yield q.get(timeout=1.0)
                except queue.Empty:
                    continue
        finally:
            with self._lock:
                if q in self._subscribers:
                    self._subscribers.remove(q)
