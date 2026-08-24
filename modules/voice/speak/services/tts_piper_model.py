from __future__ import annotations

import inspect
import io
import logging
from pathlib import Path
import threading
import time
from typing import Any, Dict, Optional
import wave

from .pcm import PCM

logger = logging.getLogger("speak.tts_piper_model")


def _wav_bytes_to_pcm(wav_bytes: bytes) -> PCM:
    import soundfile as sf

    with io.BytesIO(wav_bytes) as file_obj:
        data, samplerate = sf.read(file_obj, dtype="float32")
    channels = 1 if getattr(data, "ndim", 1) == 1 else int(data.shape[1])
    return PCM(data=data, samplerate=int(samplerate), channels=channels)


def _int16_bytes_to_pcm(raw: bytes, samplerate: int, channels: int = 1) -> PCM:
    import numpy as np

    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    channels = max(1, int(channels))
    if channels > 1 and data.size % channels == 0:
        data = data.reshape((-1, channels))
    return PCM(data=data, samplerate=int(samplerate), channels=channels)


def _load_piper_api() -> tuple[Any, Any]:
    try:
        from piper import PiperVoice  # type: ignore
    except Exception:
        try:
            from piper.voice import PiperVoice  # type: ignore
        except Exception as exc:
            raise RuntimeError("piper-tts Python package is not installed") from exc

    try:
        from piper import SynthesisConfig  # type: ignore
    except Exception:
        SynthesisConfig = None
    return PiperVoice, SynthesisConfig


class PersistentPiperModel:
    def __init__(self, cfg: Any, piper_cfg: Dict[str, Any], resolved: Dict[str, Any], synth_cancel: Optional[threading.Event] = None) -> None:
        self.model_path = str(resolved.get("model_path") or piper_cfg.get("model_path") or "").strip()
        self.config_path = str(
            resolved.get("config_path") or piper_cfg.get("config_path") or f"{self.model_path}.json"
        ).strip()
        if not self.model_path:
            raise RuntimeError("piper model_path is required")
        if not Path(self.model_path).is_file():
            raise RuntimeError(f"piper model not found: {self.model_path}")
        if not self.config_path or not Path(self.config_path).is_file():
            raise RuntimeError(f"piper config not found: {self.config_path}")

        self.default_samplerate = int(piper_cfg.get("samplerate", cfg.samplerate))
        self.default_speaker = piper_cfg.get("speaker")
        self.default_length_scale = piper_cfg.get("length_scale")
        self.default_noise_scale = piper_cfg.get("noise_scale")
        self.default_noise_w = piper_cfg.get("noise_w")
        self.default_volume = float(cfg.volume)
        self._lock = threading.Lock()
        self._synth_cancel = synth_cancel

        import modules.voice.speak.services.tts as tts_mod
        loader = getattr(tts_mod, "_load_piper_api", _load_piper_api)
        PiperVoice, SynthesisConfig = loader()
        self._synthesis_config_type = SynthesisConfig
        started = time.monotonic()
        self.voice = PiperVoice.load(self.model_path, config_path=self.config_path, use_cuda=False)
        self.model_load_ms = round((time.monotonic() - started) * 1000.0, 2)
        voice_cfg = getattr(self.voice, "config", None)
        self.samplerate = int(
            getattr(voice_cfg, "sample_rate", None)
            or getattr(voice_cfg, "sample_rate_hz", None)
            or self.default_samplerate
        )
        logger.info("Persistent Piper model loaded in %.2f ms: %s", self.model_load_ms, self.model_path)

    def health(self) -> Dict[str, Any]:
        return {
            "available": True,
            "backend": "PersistentPiperModel",
            "model_path": self.model_path,
            "config_path": self.config_path,
            "samplerate": self.samplerate,
            "model_load_ms": self.model_load_ms,
        }

    def _runtime_values(self, runtime: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        runtime = runtime if isinstance(runtime, dict) else {}
        return {
            "speaker": runtime.get("speaker", self.default_speaker),
            "length_scale": runtime.get("length_scale", self.default_length_scale),
            "noise_scale": runtime.get("noise_scale", self.default_noise_scale),
            "noise_w": runtime.get("noise_w", self.default_noise_w),
            "volume": runtime.get("volume", self.default_volume),
        }

    def _new_api_config(self, values: Dict[str, Any]) -> Any:
        config_type = self._synthesis_config_type
        if config_type is None:
            return None
        try:
            params = inspect.signature(config_type).parameters
        except Exception:
            params = {}
        candidates = {
            "speaker_id": values.get("speaker"),
            "length_scale": values.get("length_scale"),
            "noise_scale": values.get("noise_scale"),
            "noise_w_scale": values.get("noise_w"),
            "volume": values.get("volume"),
            "normalize_audio": False,
        }
        kwargs = {key: value for key, value in candidates.items() if key in params and value is not None}
        try:
            return config_type(**kwargs)
        except Exception:
            return None

    def _synthesize_current_api(self, text: str, values: Dict[str, Any]) -> Optional[PCM]:
        method = getattr(self.voice, "synthesize", None)
        if method is None:
            return None
        try:
            params = inspect.signature(method).parameters
        except Exception:
            params = {}
        if "wav_file" in params:
            return None

        kwargs: Dict[str, Any] = {}
        syn_config = self._new_api_config(values)
        if syn_config is not None and "syn_config" in params:
            kwargs["syn_config"] = syn_config

        raw_parts: list[bytes] = []
        samplerate = self.samplerate
        channels = 1
        for chunk in method(text, **kwargs):
            if self._synth_cancel is not None and self._synth_cancel.is_set():
                raise RuntimeError("synthesis cancelled")
            raw = getattr(chunk, "audio_int16_bytes", None)
            if raw is None:
                raw = getattr(chunk, "audio_bytes", None)
            if raw:
                raw_parts.append(bytes(raw))
            samplerate = int(getattr(chunk, "sample_rate", samplerate) or samplerate)
            channels = int(getattr(chunk, "sample_channels", channels) or channels)
        if not raw_parts:
            raise RuntimeError("Piper produced no audio")
        return _int16_bytes_to_pcm(b"".join(raw_parts), samplerate, channels)

    def _synthesize_legacy_stream(self, text: str, values: Dict[str, Any]) -> Optional[PCM]:
        method = getattr(self.voice, "synthesize_stream_raw", None)
        if method is None:
            return None
        kwargs = {
            "speaker_id": values.get("speaker"),
            "length_scale": values.get("length_scale"),
            "noise_scale": values.get("noise_scale"),
            "noise_w": values.get("noise_w"),
        }
        try:
            params = inspect.signature(method).parameters
            kwargs = {key: value for key, value in kwargs.items() if key in params and value is not None}
        except Exception:
            kwargs = {key: value for key, value in kwargs.items() if value is not None}
        raw_parts: list[bytes] = []
        for raw in method(text, **kwargs):
            if self._synth_cancel is not None and self._synth_cancel.is_set():
                raise RuntimeError("synthesis cancelled")
            raw_parts.append(bytes(raw))
        if not raw_parts:
            raise RuntimeError("Piper produced no audio")
        return _int16_bytes_to_pcm(b"".join(raw_parts), self.samplerate, 1)

    def _synthesize_legacy_wav(self, text: str, values: Dict[str, Any]) -> PCM:
        output = io.BytesIO()
        with wave.open(output, "wb") as wav_file:
            kwargs = {
                "speaker_id": values.get("speaker"),
                "length_scale": values.get("length_scale"),
                "noise_scale": values.get("noise_scale"),
                "noise_w": values.get("noise_w"),
            }
            method = getattr(self.voice, "synthesize", None)
            if method is None:
                raise RuntimeError("unsupported Piper Python API")
            try:
                params = inspect.signature(method).parameters
                kwargs = {key: value for key, value in kwargs.items() if key in params and value is not None}
            except Exception:
                kwargs = {key: value for key, value in kwargs.items() if value is not None}
            method(text, wav_file, **kwargs)
        import modules.voice.speak.services.tts as tts_mod
        wav_converter = getattr(tts_mod, "_wav_bytes_to_pcm", _wav_bytes_to_pcm)
        return wav_converter(output.getvalue())

    def synthesize(self, text: str, runtime: Optional[Dict[str, Any]] = None) -> PCM:
        text = str(text or "").strip()
        if not text:
            raise ValueError("text is empty")
        values = self._runtime_values(runtime)
        with self._lock:
            if self._synth_cancel is not None and self._synth_cancel.is_set():
                raise RuntimeError("synthesis cancelled")
            pcm = self._synthesize_current_api(text, values)
            if pcm is None:
                pcm = self._synthesize_legacy_stream(text, values)
            if pcm is None:
                pcm = self._synthesize_legacy_wav(text, values)
            return pcm
