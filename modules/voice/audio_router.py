"""Audio Device Router for SentryBOT.

Single I2S capture → multi-consumer (SpeechRecognition, OpenWakeWordRunner, DoAEstimator).
Solves ALSA EBUSY when multiple modules try to open the same I2S device.
"""

from __future__ import annotations

import asyncio
import logging
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, List, Optional, Protocol

import numpy as np

logger = logging.getLogger("voice.audio_router")


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
    """Single audio capture with multi-consumer dispatch."""
    
    def __init__(self, config: AudioConfig):
        self.config = config
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Consumers: name -> (consumer, callback)
        self._consumers: Dict[str, tuple[AudioConsumer, Callable[[np.ndarray, float], None]]] = {}
        self._consumers_lock = threading.RLock()
        
        # Shared VAD
        self._vad = SharedVAD(config.vad_threshold)
        
        # Audio stream
        self._stream = None
        self._pyaudio = None
        
        # Stats
        self._frames_captured = 0
        self._frames_dropped = 0
        self._last_frame_time = 0.0
    
    def register_consumer(self, name: str, consumer: AudioConsumer, 
                          callback: Optional[Callable[[np.ndarray, float], None]] = None) -> None:
        """Register an audio consumer."""
        with self._consumers_lock:
            if callback is None:
                cb = consumer.on_audio_frame
            else:
                cb = callback
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
    
    def start(self) -> bool:
        """Start audio capture."""
        if self._running:
            logger.warning("Audio capture already running")
            return False
        
        try:
            import pyaudio
            self._pyaudio = pyaudio.PyAudio()
            
            # Find device
            device_index = self._find_device()
            if device_index is None:
                logger.error("Audio device not found: %s", self.config.device)
                return False
            
            # Open stream
            fmt = pyaudio.paInt16 if self.config.format == "int16" else pyaudio.paFloat32
            self._stream = self._pyaudio.open(
                format=fmt,
                channels=self.config.channels,
                rate=self.config.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.config.frame_size,
                stream_callback=self._audio_callback,
            )
            
            self._running = True
            self._stop_event.clear()
            logger.info("Audio capture started (device=%d, rate=%d, ch=%d)", 
                       device_index, self.config.sample_rate, self.config.channels)
            return True
            
        except Exception as e:
            logger.error("Failed to start audio capture: %s", e)
            self._cleanup()
            return False
    
    def stop(self) -> None:
        """Stop audio capture."""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
        
        self._cleanup()
        
        # Notify consumers
        with self._consumers_lock:
            for name, (consumer, _) in self._consumers.items():
                try:
                    consumer.on_stop()
                except Exception as e:
                    logger.error("Consumer %s on_stop error: %s", name, e)
        
        logger.info("Audio capture stopped (frames=%d, dropped=%d)", 
                   self._frames_captured, self._frames_dropped)
    
    def _cleanup(self) -> None:
        if self._stream:
            try:
                self._stream.close()
            except Exception:
                pass
        if self._pyaudio:
            try:
                self._pyaudio.terminate()
            except Exception:
                pass
        self._stream = None
        self._pyaudio = None
    
    def _find_device(self) -> Optional[int]:
        """Find audio device index by name."""
        if not self._pyaudio:
            return None
        
        for i in range(self._pyaudio.get_device_count()):
            info = self._pyaudio.get_device_info_by_index(i)
            if self.config.device.lower() in info["name"].lower():
                if info["maxInputChannels"] >= self.config.channels:
                    return i
        
        # Fallback: default input device
        try:
            default = self._pyaudio.get_default_input_device_info()
            return int(default["index"])
        except Exception:
            return None
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio callback - called from audio thread."""
        # pyaudio is imported lazily inside start(); use numeric portaudio
        # constants here to avoid a NameError in the audio thread:
        #   paContinue == 0, paComplete == 1
        if not self._running:
            return (None, 1)
        
        try:
            # Parse audio data
            if self.config.format == "int16":
                frame = np.frombuffer(in_data, dtype=np.int16)
            else:
                frame = np.frombuffer(in_data, dtype=np.float32)
            
            # Reshape to (frames, channels)
            frame = frame.reshape(-1, self.config.channels)
            
            timestamp = time.time()
            self._frames_captured += 1
            self._last_frame_time = timestamp
            
            # VAD processing
            # Use first channel for VAD
            vad_mono = frame[:, 0] if frame.shape[1] > 0 else frame.flatten()
            is_speech = self._vad.process(vad_mono)
            
            # Dispatch to consumers
            with self._consumers_lock:
                for name, (consumer, callback) in self._consumers.items():
                    try:
                        callback(frame, timestamp)
                    except Exception as e:
                        logger.error("Consumer %s callback error: %s", name, e)
            
        except Exception as e:
            logger.error("Audio callback error: %s", e)
            self._frames_dropped += 1

        return (None, 0)

    def stream(self, maxsize: int = 64) -> Generator[bytes, None, None]:
        """Yield raw audio byte chunks (pull-style consumer API).

        Feeds a bounded queue from the capture callback; on overflow the
        oldest chunk is dropped so consumers always receive recent audio.
        The internal pump consumer is unregistered when the generator is
        closed (GC or explicit close()).
        """
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
                try:
                    yield chunk_q.get(timeout=0.25)
                except queue.Empty:
                    continue
        finally:
            self.unregister_consumer(pump_name)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "frames_captured": self._frames_captured,
            "frames_dropped": self._frames_dropped,
            "last_frame_time": self._last_frame_time,
            "consumers": list(self._consumers.keys()),
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
                logger.warning("Audio router already running, ignoring re-init")
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
                logger.error("Failed to start audio capture")
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
    """Adapter to make OpenWakeWordRunner compatible with AudioConsumer."""
    
    def __init__(self, runner):
        self.runner = runner
    
    def on_start(self) -> None:
        logger.debug("OpenWakeWordConsumerAdapter started")
        if hasattr(self.runner, 'start'):
            self.runner.start()
    
    def on_stop(self) -> None:
        logger.debug("OpenWakeWordConsumerAdapter stopped")
        if hasattr(self.runner, 'stop'):
            self.runner.stop()
    
    def on_audio_frame(self, frame: np.ndarray, timestamp: float) -> None:
        # OpenWakeWord expects mono float32
        if frame.shape[1] > 1:
            mono = frame[:, 0].astype(np.float32) / 32768.0
        else:
            mono = frame.flatten().astype(np.float32) / 32768.0
        
        try:
            if hasattr(self.runner, 'process_frame'):
                self.runner.process_frame(mono)
        except Exception as e:
            logger.debug("OpenWakeWord process_frame error: %s", e)


class DoAConsumerAdapter:
    """Adapter for Direction of Arrival estimation."""
    
    def __init__(self, doa_estimator):
        self.doa = doa_estimator
    
    def on_start(self) -> None:
        logger.debug("DoAConsumerAdapter started")
    
    def on_stop(self) -> None:
        logger.debug("DoAConsumerAdapter stopped")
    
    def on_audio_frame(self, frame: np.ndarray, timestamp: float) -> None:
        # DoA expects multi-channel audio
        try:
            if hasattr(self.doa, 'process_frame'):
                self.doa.process_frame(frame)
        except Exception as e:
            logger.debug("DoA process_frame error: %s", e)


# =============================================================================
# Helper Functions
# =============================================================================

_global_router: Optional[AudioRouter] = None
_router_lock = threading.Lock()


def _config_from_agent_yaml() -> Optional[AudioRouterConfig]:
    """Load the shared ``audio_router:`` section from agent.yaml (R18).

    Gives operators a single place to pin device/rate/channels for the one
    canonical capture path; absent section keeps dataclass defaults.
    """
    try:
        from modules.common.config_loader import load_agent_config

        cfg = load_agent_config(None).get("audio_router")
        if not isinstance(cfg, dict):
            return None
        cap = cfg.get("capture", {}) if isinstance(cfg.get("capture"), dict) else {}
        audio = AudioConfig(
            device=str(cap.get("device", "default")),
            sample_rate=int(cap.get("samplerate", cap.get("sample_rate", 16000))),
            channels=int(cap.get("channels", 2)),
            frame_size=int(cap.get("frame_size", 1024)),
        )
        return AudioRouterConfig(capture=audio)
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
    "start_audio_capture",
    "stop_audio_capture",
    "register_audio_consumer",
    "unregister_audio_consumer",
    "OpenWakeWordConsumerAdapter",
    "DoAConsumerAdapter",
]