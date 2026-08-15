from __future__ import annotations

import base64
import copy
import inspect
import io
import logging
import os
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from .lang_detect import (
    has_piper_voice_for_language,
    normalize_lang,
    piper_voice_for_language,
    resolve_speak_language,
)
from .pcm import PCM

logger = logging.getLogger("speak.tts")
_synth_cancel = threading.Event()


def cancel_synthesis() -> None:
    _synth_cancel.set()


def clear_synthesis_cancel() -> None:
    _synth_cancel.clear()


@dataclass
class TTSConfig:
    engine: str = "piper"
    language: str = "tr"
    voice: Optional[str] = None
    rate: int = 170
    volume: float = 1.0
    samplerate: int = 22050


class TTSUnavailableError(RuntimeError):
    pass


class TTSBackend:
    def synthesize(self, text: str, **_: Any) -> PCM:
        raise NotImplementedError

    def health(self) -> Dict[str, Any]:
        return {"available": True, "backend": self.__class__.__name__}


class UnavailableBackend(TTSBackend):
    def __init__(self, cfg: TTSConfig, reason: str) -> None:
        self.samplerate = int(cfg.samplerate)
        self.engine = str(cfg.engine)
        self.reason = str(reason or "tts backend unavailable")

    def synthesize(self, text: str, **_: Any) -> PCM:
        raise TTSUnavailableError(self.reason)

    def health(self) -> Dict[str, Any]:
        return {
            "available": False,
            "backend": self.__class__.__name__,
            "engine": self.engine,
            "error": self.reason,
        }


class DummyBackend(TTSBackend):
    def __init__(self, cfg: TTSConfig) -> None:
        self.samplerate = int(cfg.samplerate)

    def synthesize(self, text: str, **_: Any) -> PCM:
        import numpy as np

        seconds = max(0.2, min(1.0, len(text) * 0.03))
        t = np.linspace(0, seconds, int(self.samplerate * seconds), endpoint=False)
        data = 0.2 * np.sin(2 * np.pi * 440.0 * t).astype(np.float32)
        return PCM(data=data, samplerate=self.samplerate, channels=1)


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


def _dummy_allowed(cfg: Dict[str, Any]) -> bool:
    requested = bool(cfg.get("allow_dummy_fallback", False))
    explicit_test = str(os.getenv("SENTRYBOT_ALLOW_TEST_TTS", "")).lower() in {"1", "true", "yes", "on"}
    return requested and explicit_test


def _load_piper_api() -> tuple[Any, Any]:
    try:
        from piper import PiperVoice  # type: ignore
    except Exception:
        try:
            from piper.voice import PiperVoice  # type: ignore
        except Exception as exc:
            raise TTSUnavailableError("piper-tts Python package is not installed") from exc

    try:
        from piper import SynthesisConfig  # type: ignore
    except Exception:
        SynthesisConfig = None
    return PiperVoice, SynthesisConfig


class PersistentPiperModel:
    def __init__(self, cfg: TTSConfig, piper_cfg: Dict[str, Any], resolved: Dict[str, Any]) -> None:
        self.model_path = str(resolved.get("model_path") or piper_cfg.get("model_path") or "").strip()
        self.config_path = str(
            resolved.get("config_path") or piper_cfg.get("config_path") or f"{self.model_path}.json"
        ).strip()
        if not self.model_path:
            raise TTSUnavailableError("piper model_path is required")
        if not Path(self.model_path).is_file():
            raise TTSUnavailableError(f"piper model not found: {self.model_path}")
        if not self.config_path or not Path(self.config_path).is_file():
            raise TTSUnavailableError(f"piper config not found: {self.config_path}")

        self.default_samplerate = int(piper_cfg.get("samplerate", cfg.samplerate))
        self.default_speaker = piper_cfg.get("speaker")
        self.default_length_scale = piper_cfg.get("length_scale")
        self.default_noise_scale = piper_cfg.get("noise_scale")
        self.default_noise_w = piper_cfg.get("noise_w")
        self.default_volume = float(cfg.volume)
        self._lock = threading.Lock()

        PiperVoice, SynthesisConfig = _load_piper_api()
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
            if _synth_cancel.is_set():
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
            if _synth_cancel.is_set():
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
        return _wav_bytes_to_pcm(output.getvalue())

    def synthesize(self, text: str, runtime: Optional[Dict[str, Any]] = None) -> PCM:
        text = str(text or "").strip()
        if not text:
            raise ValueError("text is empty")
        values = self._runtime_values(runtime)
        with self._lock:
            if _synth_cancel.is_set():
                raise RuntimeError("synthesis cancelled")
            pcm = self._synthesize_current_api(text, values)
            if pcm is None:
                pcm = self._synthesize_legacy_stream(text, values)
            if pcm is None:
                pcm = self._synthesize_legacy_wav(text, values)
            return pcm


class PiperBackend(TTSBackend):
    def __init__(self, cfg: TTSConfig, piper_cfg: Dict[str, Any]) -> None:
        self.tcfg = cfg
        self.piper_cfg = copy.deepcopy(piper_cfg)
        self.default_voice = str(piper_cfg.get("voice", "tr")).strip().lower() or "tr"
        self._models: Dict[str, PersistentPiperModel] = {}
        self._ensure_model(self.default_voice)
        preload = piper_cfg.get("preload_voices", [])
        if isinstance(preload, list):
            for voice_key in preload:
                key = str(voice_key or "").strip().lower()
                if key and key != self.default_voice:
                    try:
                        self._ensure_model(key)
                    except Exception as exc:
                        logger.warning("Piper preload skipped for voice=%s: %s", key, exc)

    def _voice_cfg(self, voice_key: str) -> Dict[str, Any]:
        voices = self.piper_cfg.get("voices", {})
        if not isinstance(voices, dict):
            return {}
        entry = voices.get(voice_key)
        return dict(entry) if isinstance(entry, dict) else {}

    def _ensure_model(self, voice_key: str) -> PersistentPiperModel:
        key = str(voice_key or self.default_voice).strip().lower() or self.default_voice
        model = self._models.get(key)
        if model is not None:
            return model
        resolved = self._voice_cfg(key)
        try:
            model = PersistentPiperModel(self.tcfg, self.piper_cfg, resolved)
        except Exception:
            if key != self.default_voice:
                logger.warning("Piper voice %s unavailable; using %s", key, self.default_voice)
                return self._ensure_model(self.default_voice)
            raise
        self._models[key] = model
        return model

    def synthesize(
        self,
        text: str,
        voice_key: Optional[str] = None,
        runtime: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> PCM:
        key = str(voice_key or self.default_voice).strip().lower() or self.default_voice
        return self._ensure_model(key).synthesize(text, runtime=runtime)

    def health(self) -> Dict[str, Any]:
        return {
            "available": True,
            "backend": self.__class__.__name__,
            "default_voice": self.default_voice,
            "loaded_voices": {key: model.health() for key, model in self._models.items()},
        }


class XTTSHttpBackend(TTSBackend):
    def __init__(self, cfg: TTSConfig, xtts_cfg: Dict[str, Any]) -> None:
        self.samplerate = int(xtts_cfg.get("samplerate", cfg.samplerate))
        self.endpoint = str(xtts_cfg.get("endpoint", "")).strip()
        self.timeout = float(xtts_cfg.get("timeout", 120.0))
        self.default_speaker_wav = xtts_cfg.get("speaker_wav")
        self.default_language = str(xtts_cfg.get("language", cfg.language))
        if not self.endpoint:
            raise TTSUnavailableError("xtts endpoint is required")

    def synthesize(
        self,
        text: str,
        speaker_wav: Optional[str] = None,
        language: Optional[str] = None,
        **_: Any,
    ) -> PCM:
        payload: Dict[str, Any] = {"text": text, "language": language or self.default_language}
        wav = speaker_wav or self.default_speaker_wav
        if wav:
            payload["speaker_wav"] = wav
        response = requests.post(self.endpoint, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return _wav_bytes_to_pcm(response.content)


class RemoteTTSHttpBackend(TTSBackend):
    def __init__(self, cfg: TTSConfig, full_cfg: Dict[str, Any]) -> None:
        remote_cfg = full_cfg.get("remote", {}) if isinstance(full_cfg.get("remote"), dict) else {}
        self.endpoint = str(remote_cfg.get("endpoint", "")).strip()
        self.timeout = float(remote_cfg.get("timeout", 120.0))
        self.auth_token = str(remote_cfg.get("auth_token", "")).strip()
        self.engine = str(cfg.engine).strip().lower()
        self.default_language = str(cfg.language)
        self.piper_cfg = copy.deepcopy(full_cfg.get("piper", {}))
        self.xtts_cfg = copy.deepcopy(full_cfg.get("xtts", {}))
        self.default_speaker_wav = self.xtts_cfg.get("speaker_wav")
        if not bool(remote_cfg.get("enabled", False)) or not self.endpoint:
            raise TTSUnavailableError("remote TTS is not configured")

    def synthesize(
        self,
        text: str,
        speaker_wav: Optional[str] = None,
        language: Optional[str] = None,
        **_: Any,
    ) -> PCM:
        payload: Dict[str, Any] = {
            "text": text,
            "engine": self.engine,
            "language": language or self.default_language,
            "piper": self.piper_cfg,
            "xtts": self.xtts_cfg,
        }
        wav = speaker_wav or self.default_speaker_wav
        if wav:
            payload["speaker_wav"] = wav
        headers = {"Authorization": f"Bearer {self.auth_token}"} if self.auth_token else {}
        response = requests.post(self.endpoint, json=payload, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        content_type = str(response.headers.get("content-type", "")).lower()
        if "application/json" in content_type:
            data = response.json()
            encoded = str(data.get("wav_base64") or data.get("audio_base64") or data.get("data") or "")
            if not encoded:
                raise RuntimeError("remote TTS returned no audio")
            return _wav_bytes_to_pcm(base64.b64decode(encoded))
        return _wav_bytes_to_pcm(response.content)


class TextToSpeech:
    def __init__(self, cfg: Dict[str, Any]) -> None:
        self._base_cfg = copy.deepcopy(cfg)
        self.backend = self._build_backend(self._base_cfg)

    def _tts_config(self, cfg: Dict[str, Any]) -> TTSConfig:
        return TTSConfig(
            engine=str(cfg.get("engine", "piper")).strip().lower(),
            language=str(cfg.get("language", "tr")),
            voice=cfg.get("voice"),
            rate=int(cfg.get("rate", 170)),
            volume=float(cfg.get("volume", 1.0)),
            samplerate=int(cfg.get("samplerate", 22050)),
        )

    def _build_backend(self, cfg: Dict[str, Any]) -> TTSBackend:
        tcfg = self._tts_config(cfg)
        remote_cfg = cfg.get("remote", {}) if isinstance(cfg.get("remote"), dict) else {}
        try:
            if tcfg.engine == "dummy":
                if _dummy_allowed(cfg):
                    return DummyBackend(tcfg)
                return UnavailableBackend(tcfg, "dummy TTS is disabled")
            if tcfg.engine in {"piper", "xtts"} and bool(remote_cfg.get("enabled", False)):
                return RemoteTTSHttpBackend(tcfg, cfg)
            if tcfg.engine == "piper":
                return PiperBackend(tcfg, cfg.get("piper", {}) if isinstance(cfg.get("piper"), dict) else {})
            if tcfg.engine == "xtts":
                return XTTSHttpBackend(tcfg, cfg.get("xtts", {}) if isinstance(cfg.get("xtts"), dict) else {})
            return UnavailableBackend(tcfg, f"unsupported TTS engine: {tcfg.engine}")
        except Exception as exc:
            reason = str(exc)
            if _dummy_allowed(cfg):
                logger.warning("TTS unavailable (%s); explicit test dummy enabled", reason)
                return DummyBackend(tcfg)
            logger.warning("TTS unavailable: %s", reason)
            return UnavailableBackend(tcfg, reason)

    def is_available(self) -> bool:
        return not isinstance(self.backend, UnavailableBackend)

    def health(self) -> Dict[str, Any]:
        health = self.backend.health()
        health.setdefault("available", self.is_available())
        health.setdefault("engine", str(self._base_cfg.get("engine", "")))
        return health

    def _merge(self, overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        merged = copy.deepcopy(self._base_cfg)
        if not isinstance(overrides, dict):
            return merged
        for key, value in overrides.items():
            if key in {"piper", "xtts", "remote"} and isinstance(value, dict):
                base = merged.get(key, {}) if isinstance(merged.get(key), dict) else {}
                merged[key] = {**base, **value}
            else:
                merged[key] = value
        return merged

    def _resolve_piper_voice(self, text: str, cfg: Dict[str, Any], overrides: Optional[Dict[str, Any]]) -> Optional[str]:
        piper_cfg = cfg.get("piper", {}) if isinstance(cfg.get("piper"), dict) else {}
        if not bool(piper_cfg.get("auto_language", True)):
            return None
        explicit = overrides.get("language") if isinstance(overrides, dict) else None
        if explicit and bool(piper_cfg.get("lock_session_language", True)):
            language = normalize_lang(explicit, fallback=str(cfg.get("language", "tr")))
        else:
            language = resolve_speak_language(
                text,
                explicit=explicit,
                default=str(cfg.get("language", "tr")),
                prefer_text=bool(piper_cfg.get("prefer_text_language", False)),
            )
        if not has_piper_voice_for_language(language, piper_cfg):
            fallback_engine = str(piper_cfg.get("fallback_engine", "")).strip().lower()
            if fallback_engine:
                raise TTSUnavailableError(f"no Piper voice for language={language}; fallback={fallback_engine} is not active")
        return piper_voice_for_language(language, piper_cfg)

    def synthesize(self, text: str, overrides: Optional[Dict[str, Any]] = None) -> PCM:
        cfg = self._merge(overrides)
        requested_engine = str(cfg.get("engine", "piper")).strip().lower()
        base_engine = str(self._base_cfg.get("engine", "piper")).strip().lower()
        backend = self.backend if requested_engine == base_engine else self._build_backend(cfg)

        if isinstance(backend, PiperBackend):
            voice_key = self._resolve_piper_voice(text, cfg, overrides)
            runtime = cfg.get("piper", {}) if isinstance(cfg.get("piper"), dict) else {}
            return backend.synthesize(text, voice_key=voice_key, runtime=runtime)
        if isinstance(backend, (XTTSHttpBackend, RemoteTTSHttpBackend)):
            speaker_wav = overrides.get("speaker_wav") if isinstance(overrides, dict) else None
            language = overrides.get("language") if isinstance(overrides, dict) else None
            return backend.synthesize(text, speaker_wav=speaker_wav, language=language)
        return backend.synthesize(text)

    _resolve_piper_voice_key = _resolve_piper_voice


__all__ = [
    "TextToSpeech",
    "TTSUnavailableError",
    "cancel_synthesis",
    "clear_synthesis_cancel",
]
