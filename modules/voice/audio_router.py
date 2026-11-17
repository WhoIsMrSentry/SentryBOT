"""Audio Device Router for SentryBOT.

Single I2S capture → multi-consumer (SpeechRecognition, OpenWakeWordRunner, DoAEstimator).
Solves ALSA EBUSY when multiple modules try to open the same I2S device.
"""

from __future__ import annotations

import logging
import queue
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, Optional, Protocol

import numpy as np

logger = logging.getLogger("voice.audio_router")


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
    if text.lower() in {"", "none", "null", "default"}:
        return None
    if text.isdigit():
        return int(text)
    return device


# =============================================================================
# Protocols & Types
# =============================================================================

class AudioConsumer(Protocol):
    """Interface for audio frame consumers."""
    
    def on_audio_frame(self, frame: np.ndarray, timestamp: float) -> None:
        """Called for each audio frame."""
        ...
    
    def on_start(self) -> None:
        """Called when capture starts."""
        ...
    
    def on_stop(self) -> None:
        """Called when capture stops."""
        ...


@dataclass
class AudioConfig:
    """Audio capture configuration."""
    device: str = "default"
    sample_rate: int = 16000
    channels: int = 2  # Stereo required for DoA
    frame_size: int = 1024  # frames per buffer
    format: str = "int16"  # or "float32"
    vad_enabled: bool = True
    vad_threshold: float = 0.01


@dataclass
class AudioRouterConfig:
    """Router configuration."""
    capture: AudioConfig = field(default_factory=AudioConfig)
    # Consumer registration happens at runtime via register_consumer()


# =============================================================================
# VAD (Voice Activity Detection) - Shared
# =============================================================================

class SharedVAD:
    """Shared VAD state for all consumers."""
    
    def __init__(self, threshold: float = 0.01):
        self.threshold = threshold
        self._lock = threading.Lock()
        self._last_voice_time: float = 0
        self._is_speaking: bool = False
    
    def process(self, frame: np.ndarray) -> bool:
        """Check if frame contains voice. Returns True if voice detected."""
        # Simple energy-based VAD
        if frame.dtype == np.int16:
            energy = np.mean(np.abs(frame.astype(np.float32))) / 32768.0
        else:
            energy = np.mean(np.abs(frame))
        
        has_voice = energy > self.threshold
        
        with self._lock:
            now = time.time()
            if has_voice:
                self._last_voice_time = now
                self._is_speaking = True
            elif now - self._last_voice_time > 0.5:  # 500ms hangover
                self._is_speaking = False
            return self._is_speaking
    
    @property
    def is_speaking(self) -> bool:
        with self._lock:
            return self._is_speaking


# =============================================================================
# Audio Capture (ALSA/PulseAudio backend)
# =============================================================================

class AudioCapture:
    """Single audio capture with lock-free RT queue and worker-thread dispatch."""

    def __init__(self, config: AudioConfig):
        self.config = config
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._alsa_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._state_lock = threading.RLock()

        # Consumers: name -> (consumer, callback)
        self._consumers: Dict[str, tuple[AudioConsumer, Callable[[np.ndarray, float], None]]] = {}
        self._consumers_lock = threading.RLock()

        # Lock-free RT handoff queue: RT callback only enqueues raw bytes
        self._raw_queue: "queue.Queue[Optional[tuple[bytes, float]]]" = queue.Queue(maxsize=128)

        # Shared VAD
        self._vad = SharedVAD(config.vad_threshold)

        # Audio stream / backends
        self._active_channels = max(1, int(getattr(config, "channels", 1) or 1))
        self._stream = None
        self._pyaudio = None
        self._sd_stream = None
        self._pcm = None

        # Stats
        self._frames_captured = 0
        self._frames_dropped = 0
        self._last_frame_time = 0.0

    def register_consumer(
        self,
        name: str,
        consumer: AudioConsumer,
        callback: Optional[Callable[[np.ndarray, float], None]] = None,
    ) -> None:
        """Register an audio consumer."""
        with self._consumers_lock:
            cb = consumer.on_audio_frame if callback is None else callback
            self._consumers[name] = (consumer, cb)
            logger.info("Audio consumer registered: %s", name)

    def unregister_consumer(self, name: str) -> bool:
        """Unregister an audio consumer."""
        with self._consumers_lock:
            if name in self._consumers:
                del self._consumers[name]
                logger.info("Audio consumer unregistered: %s", name)
                return True
            return False

    def _enqueue_raw_chunk(self, raw_bytes: bytes, ts: float) -> None:
        """Push raw audio bytes without acquiring consumer/VAD locks in RT thread."""
        try:
            self._raw_queue.put_nowait((raw_bytes, ts))
        except queue.Full:
            self._frames_dropped += 1
            try:
                self._raw_queue.get_nowait()
                self._raw_queue.put_nowait((raw_bytes, ts))
            except Exception:
                pass

    def _dispatch_loop(self) -> None:
        """Worker thread: convert frames, update SharedVAD, notify consumers."""
        dtype = np.int16 if self.config.format == "int16" else np.float32
        target_ch = max(1, int(self.config.channels))
        while not self._stop_event.is_set() or not self._raw_queue.empty():
            try:
                item = self._raw_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if item is None:
                break
            raw_bytes, timestamp = item
            try:
                active_ch = max(1, int(getattr(self, "_active_channels", target_ch)))
                frame = np.frombuffer(raw_bytes, dtype=dtype)
                usable = (frame.size // active_ch) * active_ch
                if usable <= 0:
                    continue
                frame = frame[:usable].reshape(-1, active_ch)
                if active_ch == 1 and target_ch > 1:
                    frame = np.repeat(frame, target_ch, axis=1)

                self._frames_captured += 1
                self._last_frame_time = timestamp

                vad_mono = frame[:, 0] if frame.shape[1] > 0 else frame.flatten()
                self._vad.process(vad_mono)

                with self._consumers_lock:
                    consumers = list(self._consumers.items())
                for name, (_consumer, callback) in consumers:
                    try:
                        callback(frame, timestamp)
                    except Exception as exc:
                        logger.error("Consumer %s callback error: %s", name, exc)
            except Exception as exc:
                logger.error("Audio dispatch error: %s", exc)
                self._frames_dropped += 1

    def _start_alsa(self) -> bool:
        try:
            import alsaaudio  # type: ignore
        except Exception:
            return False
        try:
            fmt = (
                alsaaudio.PCM_FORMAT_S16_LE
                if self.config.format == "int16"
                else alsaaudio.PCM_FORMAT_FLOAT_LE
            )
            dev_name = str(self.config.device or "default")
            self._pcm = alsaaudio.PCM(
                type=alsaaudio.PCM_CAPTURE,
                device=dev_name,
                channels=self.config.channels,
                rate=self.config.sample_rate,
                format=fmt,
                periodsize=max(64, int(self.config.frame_size)),
            )

            def _alsa_reader() -> None:
                while not self._stop_event.is_set() and self._running:
                    pcm = self._pcm
                    if pcm is None:
                        break
                    try:
                        length, data = pcm.read()
                    except Exception:
                        break
                    if length > 0 and data:
                        self._enqueue_raw_chunk(bytes(data), time.time())

            self._alsa_thread = threading.Thread(target=_alsa_reader, daemon=True)
            self._alsa_thread.start()
            logger.info(
                "Audio capture started (ALSA): device=%s, rate=%d, ch=%d",
                dev_name,
                self.config.sample_rate,
                self.config.channels,
            )
            return True
        except Exception as exc:
            logger.debug("ALSA capture failed for %s: %s", self.config.device, exc)
            self._pcm = None
            self._alsa_thread = None
            return False

    def _start_pyaudio(self) -> bool:
        try:
            import pyaudio  # type: ignore
        except Exception:
            return False
        try:
            self._pyaudio = pyaudio.PyAudio()
            device_index = self._find_device()
            if device_index is None:
                logger.error("Audio device not found: %s", self.config.device)
                self._cleanup()
                return False

            fmt = pyaudio.paInt16 if self.config.format == "int16" else pyaudio.paFloat32
            req_ch = max(1, int(self.config.channels))
            try:
                dev_info = self._pyaudio.get_device_info_by_index(device_index)
                max_in = int(dev_info.get("maxInputChannels", 0) or 0)
            except Exception:
                max_in = 0
            preferred_ch = min(req_ch, max_in) if max_in > 0 else req_ch
            ch_candidates = [preferred_ch] + ([1] if preferred_ch > 1 else [])
            last_exc = None
            for cap_ch in ch_candidates:
                try:
                    self._active_channels = cap_ch
                    self._stream = self._pyaudio.open(
                        format=fmt,
                        channels=cap_ch,
                        rate=self.config.sample_rate,
                        input=True,
                        input_device_index=device_index,
                        frames_per_buffer=self.config.frame_size,
                        stream_callback=self._audio_callback,
                    )
                    logger.info(
                        "Audio capture started (PyAudio): device=%d, rate=%d, ch=%d%s",
                        device_index,
                        self.config.sample_rate,
                        cap_ch,
                        f" (mono->ch={req_ch})" if cap_ch != req_ch else "",
                    )
                    return True
                except Exception as exc:
                    last_exc = exc
                    self._stream = None
            if last_exc is not None:
                raise last_exc
            return False
        except Exception as exc:
            logger.debug("PyAudio capture failed: %s", exc)
            self._cleanup()
            return False

    def _start_sounddevice(self) -> bool:
        try:
            import sounddevice as sd  # type: ignore
        except Exception:
            return False
        devs = [_portaudio_device(self.config.device)]
        if self.config.device is not None:
            devs.append(None)
        req_ch = max(1, int(self.config.channels))
        for dev in devs:
            try:
                dev_info = sd.query_devices(dev, "input")
                max_in = int((dev_info or {}).get("max_input_channels", 0) or 0)
            except Exception:
                max_in = 0
            preferred_ch = min(req_ch, max_in) if max_in > 0 else req_ch
            ch_candidates = [preferred_ch] + ([1] if preferred_ch > 1 else [])
            for cap_ch in ch_candidates:
                try:
                    def _sd_cb(indata, frames, time_info, status):
                        if self._running:
                            self._enqueue_raw_chunk(bytes(indata), time.time())

                    self._active_channels = cap_ch
                    self._sd_stream = sd.InputStream(
                        device=dev,
                        channels=cap_ch,
                        samplerate=self.config.sample_rate,
                        dtype=self.config.format,
                        callback=_sd_cb,
                        blocksize=self.config.frame_size,
                    )
                    self._sd_stream.start()
                    logger.info(
                        "Audio capture started (sounddevice): device=%s, rate=%d, ch=%d%s",
                        dev if dev is not None else "default",
                        self.config.sample_rate,
                        cap_ch,
                        f" (mono->ch={req_ch})" if cap_ch != req_ch else "",
                    )
                    return True
                except Exception as exc:
                    logger.debug("sounddevice attempt failed for %s (ch=%d): %s", dev, cap_ch, exc)
                    self._sd_stream = None
        return False

    def start(self) -> bool:
        """Start audio capture and dispatch worker."""
        with self._state_lock:
            if self._running:
                logger.warning("Audio capture already running")
                return False

            self._stop_event.clear()
            while not self._raw_queue.empty():
                try:
                    self._raw_queue.get_nowait()
                except queue.Empty:
                    break
            self._running = True
            self._thread = threading.Thread(target=self._dispatch_loop, daemon=True)
            self._thread.start()

            started = False
            if _is_alsa_device_name(self.config.device):
                started = self._start_alsa() or self._start_pyaudio() or self._start_sounddevice()
            else:
                started = self._start_pyaudio() or self._start_sounddevice() or self._start_alsa()

            if not started:
                self._running = False
                self._stop_event.set()
                try:
                    self._raw_queue.put_nowait(None)
                except queue.Full:
                    pass
                if self._thread is not None:
                    self._thread.join(timeout=1.0)
                    self._thread = None
                self._cleanup()
                logger.error("Failed to start audio capture: %s", self.config.device)
                return False
            return True

    def stop(self) -> None:
        """Stop audio capture and join dispatch thread cleanly."""
        with self._state_lock:
            if not self._running and self._thread is None:
                return
            self._running = False
            self._stop_event.set()
            self._cleanup()
            try:
                self._raw_queue.put_nowait(None)
            except queue.Full:
                pass
            thr = self._thread
            alsa_thr = self._alsa_thread
            self._thread = None
            self._alsa_thread = None

        if thr is not None and thr is not threading.current_thread() and thr.is_alive():
            thr.join(timeout=1.5)
        if alsa_thr is not None and alsa_thr is not threading.current_thread() and alsa_thr.is_alive():
            alsa_thr.join(timeout=1.0)

        with self._consumers_lock:
            consumers = list(self._consumers.items())
        for name, (consumer, _) in consumers:
            try:
                consumer.on_stop()
            except Exception as exc:
                logger.error("Consumer %s on_stop error: %s", name, exc)

        logger.info(
            "Audio capture stopped (frames=%d, dropped=%d)",
            self._frames_captured,
            self._frames_dropped,
        )

    def _cleanup(self) -> None:
        if self._stream:
            try:
                self._stream.stop_stream()
            except Exception:
                pass
            try:
                self._stream.close()
            except Exception:
                pass
        if self._sd_stream:
            try:
                self._sd_stream.stop()
            except Exception:
                pass
            try:
                self._sd_stream.close()
            except Exception:
                pass
        if self._pcm:
            try:
                self._pcm.close()
            except Exception:
                pass
        if self._pyaudio:
            try:
                self._pyaudio.terminate()
            except Exception:
                pass
        self._stream = None
        self._sd_stream = None
        self._pcm = None
        self._pyaudio = None

    def _find_device(self) -> Optional[int]:
        """Find PyAudio input device index by name, numeric ID, or ALSA hw hint."""
        if not self._pyaudio:
            return None

        target = str(self.config.device or "").strip()
        target_low = target.lower()
        if target.isdigit():
            return int(target)

        hw_match = re.search(r"hw:(\d+)", target_low)
        hw_token = f"hw:{hw_match.group(1)}" if hw_match else ""

        count = self._pyaudio.get_device_count()
        for min_ch in (max(1, int(self.config.channels)), 1):
            for i in range(count):
                info = self._pyaudio.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) < min_ch:
                    continue
                name_low = str(info.get("name", "")).lower()
                if (target_low and target_low != "default" and target_low in name_low) or (hw_token and hw_token in name_low):
                    return i

        try:
            default = self._pyaudio.get_default_input_device_info()
            return int(default["index"])
        except Exception:
            return None

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """PortAudio RT callback: lock-free enqueue only (no VAD or consumer locks)."""
        if not self._running:
            return (None, 1)
        if in_data:
            self._enqueue_raw_chunk(bytes(in_data), time.time())
        return (None, 0)

    def stream(
        self,
        maxsize: int = 64,
        stop_event: Optional[threading.Event] = None,
    ) -> Generator[bytes, None, None]:
        """Yield raw audio byte chunks (pull-style consumer API)."""
        if not self._running:
            raise RuntimeError("audio capture not running")

        chunk_q: "queue.Queue[bytes]" = queue.Queue(maxsize=maxsize)
        closed = threading.Event()

        class _StreamPump:
            def on_start(self) -> None:
                pass

            def on_stop(self) -> None:
                closed.set()

            def on_audio_frame(self, frame: np.ndarray, timestamp: float) -> None:
                data = frame.tobytes()
                try:
                    chunk_q.put_nowait(data)
                except queue.Full:
                    try:
                        chunk_q.get_nowait()
                        chunk_q.put_nowait(data)
                    except Exception:
                        pass

        pump_name = f"stream-{id(chunk_q):x}"
        self.register_consumer(pump_name, _StreamPump())  # type: ignore[arg-type]
        try:
            while not closed.is_set() and self._running:
                if stop_event is not None and stop_event.is_set():
                    break
                try:
                    yield chunk_q.get(timeout=0.05)
                except queue.Empty:
                    continue
        finally:
            self.unregister_consumer(pump_name)

    def get_stats(self) -> Dict[str, Any]:
        with self._consumers_lock:
            consumers = list(self._consumers.keys())
        return {
            "running": self._running,
            "frames_captured": self._frames_captured,
            "frames_dropped": self._frames_dropped,
            "last_frame_time": self._last_frame_time,
            "consumers": consumers,
            "vad_speaking": self._vad.is_speaking,
        }


# =============================================================================
# Audio Router (Singleton)
# =============================================================================

class AudioRouter:
    """Singleton audio router managing single capture → multiple consumers."""
    
    _instance: Optional["AudioRouter"] = None
    _lock = threading.Lock()
    
    def __new__(cls, config: Optional[AudioRouterConfig] = None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config: Optional[AudioRouterConfig] = None):
        if self._initialized:
            return
        
        self.config = config or AudioRouterConfig()
        self._capture: Optional[AudioCapture] = None
        self._consumers: Dict[str, AudioConsumer] = {}
        self._lock = threading.RLock()
        self._initialized = True
        
        logger.info("AudioRouter initialized")
    
    def initialize(self, config: AudioRouterConfig) -> None:
        """Initialize with config (idempotent)."""
        with self._lock:
            if self._capture and self._capture._running:
                logger.debug("Audio router already running, ignoring re-init")
                return
            self.config = config
    
    def register_consumer(self, name: str, consumer: AudioConsumer) -> None:
        """Register a consumer (e.g., OpenWakeWordRunner, DoAEstimator)."""
        with self._lock:
            if name in self._consumers:
                logger.warning("Consumer %s already registered, replacing", name)
            self._consumers[name] = consumer
            
            # If capture already running, register immediately
            if self._capture and self._capture._running:
                self._capture.register_consumer(name, consumer)
                consumer.on_start()
    
    def unregister_consumer(self, name: str) -> bool:
        """Unregister a consumer."""
        with self._lock:
            if self._capture:
                self._capture.unregister_consumer(name)
            return self._consumers.pop(name, None) is not None
    
    def start(self) -> bool:
        """Start audio capture and notify consumers."""
        with self._lock:
            if self._capture and self._capture._running:
                return True
            
            self._capture = AudioCapture(self.config.capture)
            
            # Register existing consumers
            for name, consumer in self._consumers.items():
                self._capture.register_consumer(name, consumer)
            
            if not self._capture.start():
                logger.debug("AudioRouter: capture backend unavailable")
                self._capture = None
                return False
            
            # Notify consumers
            for name, consumer in self._consumers.items():
                try:
                    consumer.on_start()
                except Exception as e:
                    logger.error("Consumer %s on_start error: %s", name, e)
            
            return True
    
    def stop(self) -> None:
        """Stop audio capture."""
        with self._lock:
            if self._capture:
                self._capture.stop()
                self._capture = None
    
    def get_capture(self) -> Optional[AudioCapture]:
        with self._lock:
            return self._capture

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            stats = {
                "initialized": self._initialized,
                "running": self._capture is not None and self._capture._running,
                "consumers": list(self._consumers.keys()),
            }
            if self._capture:
                stats.update(self._capture.get_stats())
            return stats


# =============================================================================
# Consumer Adapters (for existing modules)
# =============================================================================

class OpenWakeWordConsumerAdapter:
    """Adapter bridging AudioCapture frames into OpenWakewordRunner."""

    def __init__(self, runner, on_detect: Optional[Callable[[str], None]] = None):
        self.runner = runner
        self.on_detect = on_detect

    def on_start(self) -> None:
        logger.debug("OpenWakeWordConsumerAdapter started")
        if hasattr(self.runner, "start"):
            self.runner.start()

    def on_stop(self) -> None:
        logger.debug("OpenWakeWordConsumerAdapter stopped")
        if hasattr(self.runner, "stop"):
            self.runner.stop()

    def on_audio_frame(self, frame: np.ndarray, timestamp: float) -> None:
        try:
            if hasattr(self.runner, "_infer_chunk"):
                pcm = frame if frame.dtype == np.int16 else (np.clip(frame, -1.0, 1.0) * 32767.0).astype(np.int16)
                label = self.runner._infer_chunk(pcm.tobytes())
                if label and self.on_detect is not None:
                    self.on_detect(label)
            elif hasattr(self.runner, "process_frame"):
                mono = (
                    frame[:, 0].astype(np.float32) / 32768.0
                    if frame.ndim > 1 and frame.shape[1] > 1
                    else frame.flatten().astype(np.float32) / 32768.0
                )
                self.runner.process_frame(mono)
        except Exception as exc:
            logger.debug("OpenWakeWord adapter frame error: %s", exc)


class DoAConsumerAdapter:
    """Adapter for Direction of Arrival estimation."""

    def __init__(self, doa_estimator, on_angle: Optional[Callable[[float], None]] = None):
        self.doa = doa_estimator
        self.on_angle = on_angle

    def on_start(self) -> None:
        logger.debug("DoAConsumerAdapter started")

    def on_stop(self) -> None:
        logger.debug("DoAConsumerAdapter stopped")

    def on_audio_frame(self, frame: np.ndarray, timestamp: float) -> None:
        try:
            if hasattr(self.doa, "estimate"):
                pcm = frame if frame.dtype == np.int16 else (np.clip(frame, -1.0, 1.0) * 32767.0).astype(np.int16)
                angle = self.doa.estimate(pcm.tobytes())
                if self.on_angle is not None:
                    self.on_angle(float(angle))
            elif hasattr(self.doa, "process_frame"):
                self.doa.process_frame(frame)
        except Exception as exc:
            logger.debug("DoA adapter frame error: %s", exc)


# =============================================================================
# Helper Functions
# =============================================================================

_global_router: Optional[AudioRouter] = None
_router_lock = threading.Lock()


def load_audio_router_config(root_cfg: Optional[Dict[str, Any]] = None) -> AudioRouterConfig:
    """Canonical loader for shared audio_router configuration from agent.yaml."""
    if root_cfg is None:
        try:
            from modules.common.config_loader import load_agent_config

            root_cfg = load_agent_config()
        except Exception:
            root_cfg = {}
    audio_router_cfg = root_cfg.get("audio_router") if isinstance(root_cfg, dict) else None
    if not isinstance(audio_router_cfg, dict):
        return AudioRouterConfig()
    cap = audio_router_cfg.get("capture", {}) if isinstance(audio_router_cfg.get("capture"), dict) else {}
    return AudioRouterConfig(
        capture=AudioConfig(
            device=str(cap.get("device", "default")),
            sample_rate=int(cap.get("samplerate", cap.get("sample_rate", 16000))),
            channels=int(cap.get("channels", 2)),
            frame_size=int(cap.get("frame_size", 1024)),
            format=str(cap.get("format", cap.get("dtype", "int16"))),
            vad_enabled=bool(cap.get("vad_enabled", True)),
            vad_threshold=float(cap.get("vad_threshold", 0.01)),
        )
    )


def _config_from_agent_yaml() -> Optional[AudioRouterConfig]:
    try:
        from modules.common.config_loader import load_agent_config

        cfg = load_agent_config(None)
        if not isinstance(cfg.get("audio_router"), dict):
            return None
        return load_audio_router_config(cfg)
    except Exception:
        return None


def get_audio_router(config: Optional[AudioRouterConfig] = None) -> AudioRouter:
    """Get global audio router instance."""
    global _global_router
    with _router_lock:
        if _global_router is None:
            _global_router = AudioRouter(config or _config_from_agent_yaml())
        elif config:
            _global_router.initialize(config)
        return _global_router


def start_audio_capture(config: Optional[AudioRouterConfig] = None) -> bool:
    """Start global audio capture."""
    router = get_audio_router(config)
    return router.start()


def stop_audio_capture() -> None:
    """Stop global audio capture."""
    global _global_router
    with _router_lock:
        if _global_router:
            _global_router.stop()


def register_audio_consumer(name: str, consumer: AudioConsumer) -> None:
    """Register a consumer with the global router."""
    router = get_audio_router()
    router.register_consumer(name, consumer)


def unregister_audio_consumer(name: str) -> bool:
    """Unregister a consumer from the global router."""
    router = get_audio_router()
    return router.unregister_consumer(name)


# =============================================================================
# Module-level exports
# =============================================================================

__all__ = [
    "AudioRouter",
    "AudioRouterConfig",
    "AudioConfig",
    "AudioCapture",
    "AudioConsumer",
    "get_audio_router",
    "load_audio_router_config",
    "start_audio_capture",
    "stop_audio_capture",
    "register_audio_consumer",
    "unregister_audio_consumer",
    "OpenWakeWordConsumerAdapter",
    "DoAConsumerAdapter",
    "_is_alsa_device_name",
    "_portaudio_device",
]