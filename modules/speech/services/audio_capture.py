from __future__ import annotations
import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Any

try:
    import sounddevice as sd
except Exception:
    sd = None
try:
    import alsaaudio
except Exception:
    alsaaudio = None

logger = logging.getLogger("speech.audio")

# GLOBAL SINGLETON for all audio capture to ensure zero contention
_SINGLE_CAPTURE_INSTANCE: Optional["AudioCapture"] = None
_INSTANCE_LOCK = threading.Lock()

def get_shared_capture(cfg: Dict) -> "AudioCapture":
    """Returns a globally shared AudioCapture instance regardless of config keys to ensure no contention."""
    global _SINGLE_CAPTURE_INSTANCE
    with _INSTANCE_LOCK:
        if _SINGLE_CAPTURE_INSTANCE is None:
            _SINGLE_CAPTURE_INSTANCE = AudioCapture(cfg)
        return _SINGLE_CAPTURE_INSTANCE

def release_shared_capture(inst: "AudioCapture") -> None:
    # In this simplified singleton model, we don't actually stop it unless explicitly told.
    pass

@dataclass
class AudioConfig:
    device: Any = None
    samplerate: int = 16000
    channels: int = 1
    dtype: str = "int16"
    frame_ms: int = 30

class AudioCapture:
    """Singleton audio capture supporting multiple broadcast subscribers."""

    def __init__(self, cfg: Dict):
        self.cfg = AudioConfig(
            device=cfg.get("device"),
            samplerate=int(cfg.get("samplerate", 16000)),
            channels=int(cfg.get("channels", 1)),
            dtype=str(cfg.get("dtype", "int16")),
            frame_ms=int(cfg.get("frame_ms", 30)),
        )
        self._subscribers: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._stream = None
        self._stopped = False
        self._alsa_thread = None
        self._pcm = None

    def _callback(self, indata, frames, time, status):
        if status:
            logger.warning("Audio status: %s", status)
        data = bytes(indata)
        with self._lock:
            for q in self._subscribers:
                try:
                    q.put_nowait(data)
                except queue.Full:
                    pass

    def start(self):
        with self._lock:
            if self._stream is not None or self._alsa_thread is not None:
                return

            blocksize = int(self.cfg.samplerate * self.cfg.frame_ms / 1000)
            
            # Try sounddevice (PortAudio)
            if sd is not None:
                # 1. Try explicit device
                devs_to_try = [self.cfg.device, None] # Try configured, then default
                for dev in devs_to_try:
                    try:
                        # Convert numeric string to int
                        actual_dev = dev
                        if isinstance(dev, str) and dev.isdigit():
                            actual_dev = int(dev)
                        
                        self._stream = sd.InputStream(
                            device=actual_dev,
                            channels=self.cfg.channels,
                            samplerate=self.cfg.samplerate,
                            dtype=self.cfg.dtype,
                            callback=self._callback,
                            blocksize=blocksize,
                        )
                        self._stream.start()
                        self._stopped = False
                        logger.info("Audio capture started (portaudio): %s @ %d Hz", actual_dev if actual_dev is not None else "default", self.cfg.samplerate)
                        return
                    except Exception as exc:
                        logger.warning("sounddevice attempt failed for device %s: %s", dev, exc)

            # Fallback: pyalsaaudio
            if alsaaudio is not None:
                try:
                    fmt = alsaaudio.PCM_FORMAT_S16_LE if self.cfg.dtype == 'int16' else alsaaudio.PCM_FORMAT_S32_LE
                    dev_name = str(self.cfg.device) if self.cfg.device is not None else "default"
                    
                    self._pcm = alsaaudio.PCM(
                        type=alsaaudio.PCM_CAPTURE,
                        device=dev_name,
                        channels=self.cfg.channels,
                        rate=self.cfg.samplerate,
                        format=fmt,
                        periodsize=max(64, blocksize)
                    )

                    def _alsa_reader():
                        self._stopped = False
                        try:
                            while not self._stopped:
                                length, data = self._pcm.read()
                                if length > 0 and data:
                                    b_data = bytes(data)
                                    with self._lock:
                                        for q in self._subscribers:
                                            try: q.put_nowait(b_data)
                                            except: pass
                        finally:
                            if self._pcm:
                                self._pcm.close()
                                self._pcm = None

                    self._alsa_thread = threading.Thread(target=_alsa_reader, daemon=True)
                    self._alsa_thread.start()
                    logger.info("Audio capture started (ALSA fallback): %s @ %d Hz", dev_name, self.cfg.samplerate)
                    return
                except Exception as exc:
                    logger.warning("ALSA fallback failed: %s", exc)

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
