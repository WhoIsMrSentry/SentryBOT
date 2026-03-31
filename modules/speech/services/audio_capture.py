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

# Shared capture registry to avoid opening the same ALSA device multiple times
_SHARED_CAPTURES: dict = {}

def get_shared_capture(cfg: Dict) -> "AudioCapture":
    device = cfg.get("device") or "default"
    key = f"{device}:{int(cfg.get('samplerate', 16000))}:{int(cfg.get('channels',1))}"
    pair = _SHARED_CAPTURES.get(key)
    if pair:
        inst, ref = pair
        _SHARED_CAPTURES[key] = (inst, ref + 1)
        return inst
    inst = AudioCapture(cfg)
    inst._shared_key = key
    _SHARED_CAPTURES[key] = (inst, 1)
    return inst

def release_shared_capture(inst: "AudioCapture") -> None:
    key = getattr(inst, "_shared_key", None)
    if not key:
        try:
            inst.stop()
        except Exception:
            pass
        return
    pair = _SHARED_CAPTURES.get(key)
    if not pair:
        try:
            inst.stop()
        except Exception:
            pass
        return
    _, ref = pair
    if ref <= 1:
        try:
            inst.stop()
        except Exception:
            pass
        del _SHARED_CAPTURES[key]
    else:
        _SHARED_CAPTURES[key] = (inst, ref - 1)


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
        self._pcm = None

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
        # If already started, do nothing (idempotent)
        if self._stream is not None:
            return
        if self._alsa_thread is not None and not self._stopped:
            return

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
                logger.warning("sounddevice InputStream failed with device %s: %s", self.cfg.device, exc)
                # Try again without explicit device (let PortAudio pick default). Useful on Windows
                try:
                    self._stream = sd.InputStream(
                        channels=self.cfg.channels,
                        samplerate=self.cfg.samplerate,
                        dtype=self.cfg.dtype,
                        callback=self._callback,
                        blocksize=blocksize,
                    )
                    self._stream.start()
                    self._stopped = False
                    logger.info("Audio capture started (portaudio, default device) @ %d Hz", self.cfg.samplerate)
                    return
                except Exception as exc2:
                    logger.warning("sounddevice InputStream default device failed: %s", exc2)

        # Fallback: use pyalsaaudio if available
        if alsaaudio is None:
            raise RuntimeError("No suitable audio backend available. Install 'sounddevice' or 'pyalsaaudio'.")

        try:
            fmt_map = {
                'int16': alsaaudio.PCM_FORMAT_S16_LE,
                'int32': alsaaudio.PCM_FORMAT_S32_LE,
            }
            fmt = fmt_map.get(self.cfg.dtype, alsaaudio.PCM_FORMAT_S16_LE)
            # store PCM on instance so shared captures don't reopen device
            # Use named parameters to avoid DeprecationWarning from pyalsaaudio
            self._pcm = alsaaudio.PCM(type=alsaaudio.PCM_CAPTURE,
                                      device=self.cfg.device,
                                      channels=self.cfg.channels,
                                      rate=self.cfg.samplerate,
                                      format=fmt,
                                      periodsize=max(64, blocksize))

            def _alsa_reader():
                self._stopped = False
                try:
                    while not self._stopped:
                        try:
                            length, data = self._pcm.read()
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
                        if self._pcm is not None:
                            self._pcm.close()
                    except Exception:
                        pass
                    self._pcm = None

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
        if self._pcm is not None:
            try:
                self._pcm.close()
            except Exception:
                pass
            self._pcm = None
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
