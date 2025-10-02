from __future__ import annotations
import logging
import queue
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

try:
    import sounddevice as sd
except Exception:  # Optional at import time; validated at runtime
    sd = None  # type: ignore

logger = logging.getLogger("speech.audio")


@dataclass
class AudioConfig:
    device: Optional[str] = None  # ALSA device name or index
    samplerate: int = 16000
    channels: int = 1             # 1=mono, 2=stereo (two I2S mics)
    dtype: str = "int16"          # PCM 16-bit
    frame_ms: int = 30            # 30ms frames (~480 samples @16k)


class AudioCapture:
    """Simple pull-based audio capture using sounddevice (PortAudio/ALSA)."""

    def __init__(self, cfg: Dict):
        self.cfg = AudioConfig(
            device=cfg.get("device"),
            samplerate=int(cfg.get("samplerate", 16000)),
            channels=int(cfg.get("channels", 1)),
            dtype=str(cfg.get("dtype", "int16")),
            frame_ms=int(cfg.get("frame_ms", 30)),
        )
        self._q: "queue.Queue[bytes]" = queue.Queue(maxsize=10)
        self._stream = None
        self._stopped = False

    def _ensure_backend(self):
        if sd is None:
            raise RuntimeError("sounddevice not available. Install with 'pip install sounddevice' and ensure ALSA devices are present.")

    def _callback(self, indata, frames, time, status):  # noqa: D401
        if status:
            logger.warning("Audio status: %s", status)
        try:
            self._q.put_nowait(bytes(indata))
        except queue.Full:
            # drop frame; recognition is resilient
            pass

    def start(self):
        self._ensure_backend()
        blocksize = int(self.cfg.samplerate * self.cfg.frame_ms / 1000)
        self._stream = sd.InputStream(
            device=self.cfg.device,
            channels=self.cfg.channels,
            samplerate=self.cfg.samplerate,
            dtype=self.cfg.dtype,
            callback=self._callback,
            blocksize=blocksize,
        )
        self._stream.start()
        self._stopped = False
        logger.info("Audio capture started: %s @ %d Hz", self.cfg.device or "default", self.cfg.samplerate)

    def stop(self):
        self._stopped = True
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None
        # drain queue
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except Exception:
                break
        logger.info("Audio capture stopped")

    def stream(self) -> Iterable[bytes]:
        """Generator yielding audio frames. Starts backend lazily."""
        if self._stream is None:
            self.start()
        while not self._stopped:
            try:
                chunk = self._q.get(timeout=1.0)
                yield chunk
            except queue.Empty:
                continue
