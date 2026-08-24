from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional
import requests

from .lang_detect import (
    has_piper_voice_for_language,
    normalize_lang,
    piper_voice_for_language,
    resolve_speak_language,
)
from .pcm import PCM
from .tts_piper_model import (
    PersistentPiperModel,
    _load_piper_api,
    _wav_bytes_to_pcm,
    _int16_bytes_to_pcm,
)
from .tts_remote_backends import TTSBackend, XTTSHttpBackend, RemoteTTSHttpBackend

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


def _dummy_allowed(cfg: Dict[str, Any]) -> bool:
    requested = bool(cfg.get("allow_dummy_fallback", False))
    explicit_test = str(os.getenv("SENTRYBOT_ALLOW_TEST_TTS", "")).lower() in {"1", "true", "yes", "on"}
    return requested and explicit_test


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
            model = PersistentPiperModel(self.tcfg, self.piper_cfg, resolved, synth_cancel=_synth_cancel)
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
        if explicit and bool(piper_cfg.get("lock_session_language", True)) and not bool(piper_cfg.get("prefer_text_language", False)):
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
            try:
                return backend.synthesize(text, speaker_wav=speaker_wav, language=language)
            except Exception as exc:
                # Remote path failed (network/timeout/cancel): degrade to the
                # local Piper engine instead of leaving the robot mute (R22).
                logger.warning("remote TTS failed (%s); falling back to local Piper", exc)
                piper_cfg = cfg.get("piper", {}) if isinstance(cfg.get("piper"), dict) else {}
                local = PiperBackend(self._tts_config(cfg), piper_cfg)
                voice_key = self._resolve_piper_voice(text, cfg, overrides)
                runtime = piper_cfg
                return local.synthesize(text, voice_key=voice_key, runtime=runtime)
        return backend.synthesize(text)

    _resolve_piper_voice_key = _resolve_piper_voice


__all__ = [
    "TextToSpeech",
    "TTSUnavailableError",
    "PersistentPiperModel",
    "PiperBackend",
    "XTTSHttpBackend",
    "RemoteTTSHttpBackend",
    "TTSBackend",
    "cancel_synthesis",
    "clear_synthesis_cancel",
]
