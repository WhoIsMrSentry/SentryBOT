from __future__ import annotations
import logging
import queue
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

try:
    import sounddevice as sd
except Exception:  # Optional at import time; validated at runtime
    sd = None  # type: ignore
try:
    import alsaaudio
except Exception:
    alsaaudio = None

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
        self._alsa_thread = None

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
        # Prefer sounddevice (PortAudio) when available, but fall back to pyalsaaudio
        blocksize = int(self.cfg.samplerate * self.cfg.frame_ms / 1000)
        if sd is not None:
            try:
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
                logger.info("Audio capture started (portaudio): %s @ %d Hz", self.cfg.device or "default", self.cfg.samplerate)
                return
            except Exception as exc:
                logger.warning("sounddevice InputStream failed, falling back to ALSA: %s", exc)

        # Fallback: use pyalsaaudio if available
        if alsaaudio is None:
            raise RuntimeError("No suitable audio backend available. Install 'sounddevice' or 'pyalsaaudio'.")

        try:
            fmt_map = {
                'int16': alsaaudio.PCM_FORMAT_S16_LE,
                'int32': alsaaudio.PCM_FORMAT_S32_LE,
            }
            fmt = fmt_map.get(self.cfg.dtype, alsaaudio.PCM_FORMAT_S16_LE)
            pcm = alsaaudio.PCM(alsaaudio.PCM_CAPTURE, device=self.cfg.device)
            pcm.setchannels(self.cfg.channels)
            pcm.setrate(self.cfg.samplerate)
            pcm.setformat(fmt)
            # period size roughly equals blocksize
            pcm.setperiodsize(max(64, blocksize))

            def _alsa_reader():
                self._stopped = False
                try:
                    while not self._stopped:
                        try:
                            length, data = pcm.read()
                            if length > 0 and data:
                                try:
                                    self._q.put_nowait(bytes(data))
                                except queue.Full:
                                    pass
                        except Exception as e:
                            logger.debug("ALSA read error: %s", e)
                            time.sleep(0.01)
                finally:
                    try:
                        pcm.close()
                    except Exception:
                        pass

            import time
            import threading
            self._alsa_thread = threading.Thread(target=_alsa_reader, daemon=True)
            self._alsa_thread.start()
            logger.info("Audio capture started (ALSA fallback): %s @ %d Hz", self.cfg.device or "default", self.cfg.samplerate)
        except Exception as exc:
            raise RuntimeError(f"ALSA fallback failed: {exc}")

    def stop(self):
        self._stopped = True
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None
        if self._alsa_thread is not None:
            try:
                self._alsa_thread.join(timeout=0.5)
            except Exception:
                pass
            self._alsa_thread = None
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
