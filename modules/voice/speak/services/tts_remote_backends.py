from __future__ import annotations

import base64
import copy
import logging
from typing import Any, Dict, Optional
import requests

from .pcm import PCM
from .tts_piper_model import _wav_bytes_to_pcm

logger = logging.getLogger("speak.tts_remote_backends")


class TTSBackend:
    def synthesize(self, text: str, **_: Any) -> PCM:
        raise NotImplementedError

    def health(self) -> Dict[str, Any]:
        return {"available": True, "backend": self.__class__.__name__}


class XTTSHttpBackend(TTSBackend):
    DEFAULT_TIMEOUT_S = 15.0

    def __init__(self, cfg: Any, xtts_cfg: Dict[str, Any]) -> None:
        self.samplerate = int(xtts_cfg.get("samplerate", cfg.samplerate))
        self.endpoint = str(xtts_cfg.get("endpoint", "")).strip()
        self.timeout = float(xtts_cfg.get("timeout", self.DEFAULT_TIMEOUT_S))
        self.default_speaker_wav = xtts_cfg.get("speaker_wav")
        self.default_language = str(xtts_cfg.get("language", cfg.language))
        if not self.endpoint:
            raise RuntimeError("xtts endpoint is required")

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
        import modules.voice.speak.services.tts as tts_mod
        req = getattr(tts_mod, "requests", requests)
        wav_converter = getattr(tts_mod, "_wav_bytes_to_pcm", _wav_bytes_to_pcm)
        self._raise_if_cancelled(tts_mod)
        response = req.post(self.endpoint, json=payload, timeout=self.timeout)
        response.raise_for_status()
        self._raise_if_cancelled(tts_mod)
        return wav_converter(response.content)

    @staticmethod
    def _raise_if_cancelled(tts_mod: Any) -> None:
        cancel = getattr(tts_mod, "_synth_cancel", None)
        if cancel is not None and cancel.is_set():
            raise RuntimeError("synthesis_cancelled")


class RemoteTTSHttpBackend(TTSBackend):
    DEFAULT_TIMEOUT_S = 15.0

    def __init__(self, cfg: Any, full_cfg: Dict[str, Any]) -> None:
        remote_cfg = full_cfg.get("remote", {}) if isinstance(full_cfg.get("remote"), dict) else {}
        self.endpoint = str(remote_cfg.get("endpoint", "")).strip()
        self.timeout = float(remote_cfg.get("timeout", self.DEFAULT_TIMEOUT_S))
        self.auth_token = str(remote_cfg.get("auth_token", "")).strip()
        self.engine = str(cfg.engine).strip().lower()
        self.default_language = str(cfg.language)
        self.piper_cfg = copy.deepcopy(full_cfg.get("piper", {}))
        self.xtts_cfg = copy.deepcopy(full_cfg.get("xtts", {}))
        self.default_speaker_wav = self.xtts_cfg.get("speaker_wav")
        if not bool(remote_cfg.get("enabled", False)) or not self.endpoint:
            raise RuntimeError("remote TTS is not configured")

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
        import modules.voice.speak.services.tts as tts_mod
        req = getattr(tts_mod, "requests", requests)
        wav_converter = getattr(tts_mod, "_wav_bytes_to_pcm", _wav_bytes_to_pcm)
        XTTSHttpBackend._raise_if_cancelled(tts_mod)
        response = req.post(self.endpoint, json=payload, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        XTTSHttpBackend._raise_if_cancelled(tts_mod)
        content_type = str(response.headers.get("content-type", "")).lower()
        if "application/json" in content_type:
            data = response.json()
            encoded = str(data.get("wav_base64") or data.get("audio_base64") or data.get("data") or "")
            if not encoded:
                raise RuntimeError("remote TTS returned no audio")
            return wav_converter(base64.b64decode(encoded))
        return wav_converter(response.content)
