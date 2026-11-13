from __future__ import annotations

import copy
from collections import OrderedDict
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path  # noqa: F401  -- tests patch tts.Path.is_file on the shared Path class
from typing import Any, Dict, Optional

import requests  # noqa: F401  -- remote backends and tests resolve requests via this module

from .lang_detect import (
    has_piper_voice_for_language,
    normalize_lang,
    piper_voice_for_language,
    resolve_speak_language,
)
from .pcm import PCM
from .tts_piper_model import (  # noqa: F401
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
        clear_synthesis_cancel()
        raw = copy.deepcopy(cfg or {})
        if "tts" in raw and isinstance(raw["tts"], dict):
            self._base_cfg = {**raw, **raw["tts"]}
        else:
            self._base_cfg = raw
        self._cache_lock = threading.Lock()
        self._pcm_cache: "OrderedDict[tuple[Any, ...], PCM]" = OrderedDict()
        self._pcm_cache_max_entries = max(0, int(self._base_cfg.get("pcm_cache_max_entries", 24)))
        self._pcm_cache_max_chars = max(1, int(self._base_cfg.get("pcm_cache_max_chars", 80)))
        self._pcm_cache_hits = 0
        self._pcm_cache_misses = 0
        self._fallback_piper: Optional[PiperBackend] = None
        self._backends_cache: Dict[tuple[Any, ...], TTSBackend] = {}
        self.backend = self._build_backend(self._base_cfg)
        base_engine = str(self._base_cfg.get("engine", "piper")).strip().lower()
        self._backends_cache[self._backend_cache_key(base_engine, self._base_cfg)] = self.backend

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
        with self._cache_lock:
            health["pcm_cache"] = {
                "entries": len(self._pcm_cache),
                "max_entries": self._pcm_cache_max_entries,
                "hits": self._pcm_cache_hits,
                "misses": self._pcm_cache_misses,
            }
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

    def _backend_cache_key(self, requested_engine: str, cfg: Dict[str, Any]) -> tuple[Any, ...]:
        remote_cfg = cfg.get("remote", {}) if isinstance(cfg.get("remote"), dict) else {}
        xtts_cfg = cfg.get("xtts", {}) if isinstance(cfg.get("xtts"), dict) else {}
        return (
            requested_engine,
            bool(remote_cfg.get("enabled", False)),
            str(remote_cfg.get("endpoint") or ""),
            str(xtts_cfg.get("endpoint") or ""),
        )

    def _get_or_build_backend(self, requested_engine: str, cfg: Dict[str, Any]) -> TTSBackend:
        key = self._backend_cache_key(requested_engine, cfg)
        base_engine = str(self._base_cfg.get("engine", "piper")).strip().lower()
        if key == self._backend_cache_key(base_engine, self._base_cfg):
            return self.backend
        cached = self._backends_cache.get(key)
        if cached is not None:
            return cached
        built = self._build_backend(cfg)
        self._backends_cache[key] = built
        return built

    def _get_fallback_piper(self, cfg: Dict[str, Any]) -> PiperBackend:
        if isinstance(self.backend, PiperBackend):
            return self.backend
        if self._fallback_piper is None:
            piper_cfg = cfg.get("piper", {}) if isinstance(cfg.get("piper"), dict) else {}
            self._fallback_piper = PiperBackend(self._tts_config(cfg), piper_cfg)
        return self._fallback_piper

    def _pcm_cache_get(self, key: tuple[Any, ...]) -> Optional[PCM]:
        if self._pcm_cache_max_entries <= 0:
            return None
        with self._cache_lock:
            hit = self._pcm_cache.get(key)
            if hit is None:
                self._pcm_cache_misses += 1
                return None
            self._pcm_cache.move_to_end(key)
            self._pcm_cache_hits += 1
            return PCM(data=hit.data.copy(), samplerate=hit.samplerate, channels=hit.channels)

    def _pcm_cache_put(self, key: tuple[Any, ...], pcm: PCM) -> None:
        if self._pcm_cache_max_entries <= 0 or _synth_cancel.is_set():
            return
        data = getattr(pcm, "data", None)
        if data is None or not hasattr(data, "copy"):
            return
        with self._cache_lock:
            self._pcm_cache[key] = PCM(data=data.copy(), samplerate=pcm.samplerate, channels=pcm.channels)
            self._pcm_cache.move_to_end(key)
            while len(self._pcm_cache) > self._pcm_cache_max_entries:
                self._pcm_cache.popitem(last=False)

    def synthesize(self, text: str, overrides: Optional[Dict[str, Any]] = None) -> PCM:
        cfg = self._merge(overrides)
        requested_engine = str(cfg.get("engine", "piper")).strip().lower()
        backend = self._get_or_build_backend(requested_engine, cfg)
        lang_hint = str((overrides or {}).get("language") or cfg.get("language") or "")

        if isinstance(backend, PiperBackend):
            voice_key = self._resolve_piper_voice(text, cfg, overrides)
            runtime = cfg.get("piper", {}) if isinstance(cfg.get("piper"), dict) else {}
            cache_key = (
                "piper",
                voice_key or backend.default_voice,
                text,
                str(runtime.get("length_scale", "")),
                str(runtime.get("noise_scale", "")),
                str(runtime.get("noise_w", "")),
            )
            if len(text) <= self._pcm_cache_max_chars:
                cached = self._pcm_cache_get(cache_key)
                if cached is not None:
                    return cached
            pcm = backend.synthesize(text, voice_key=voice_key, runtime=runtime)
            if len(text) <= self._pcm_cache_max_chars:
                self._pcm_cache_put(cache_key, pcm)
            return pcm

        if isinstance(backend, (XTTSHttpBackend, RemoteTTSHttpBackend)):
            speaker_wav = overrides.get("speaker_wav") if isinstance(overrides, dict) else None
            language = overrides.get("language") if isinstance(overrides, dict) else None
            cache_key = (backend.__class__.__name__, requested_engine, language or "", str(speaker_wav or ""), text)
            if len(text) <= self._pcm_cache_max_chars:
                cached = self._pcm_cache_get(cache_key)
                if cached is not None:
                    return cached
            try:
                pcm = backend.synthesize(text, speaker_wav=speaker_wav, language=language)
            except Exception as exc:
                if "synthesis_cancelled" in str(exc) or _synth_cancel.is_set():
                    raise
                logger.warning("remote TTS failed (%s); falling back to cached local Piper", exc)
                local = self._get_fallback_piper(cfg)
                voice_key = self._resolve_piper_voice(text, cfg, overrides)
                piper_cfg = cfg.get("piper", {}) if isinstance(cfg.get("piper"), dict) else {}
                return local.synthesize(text, voice_key=voice_key, runtime=piper_cfg)
            if len(text) <= self._pcm_cache_max_chars:
                self._pcm_cache_put(cache_key, pcm)
            return pcm

        cache_key = (backend.__class__.__name__, requested_engine, lang_hint, text)
        if len(text) <= self._pcm_cache_max_chars:
            cached = self._pcm_cache_get(cache_key)
            if cached is not None:
                return cached
        pcm = backend.synthesize(text)
        if len(text) <= self._pcm_cache_max_chars and not isinstance(backend, UnavailableBackend):
            self._pcm_cache_put(cache_key, pcm)
        return pcm

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
