from __future__ import annotations

import logging
import re
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from .models import PiperVoice, XttsSourceVoice

logger = logging.getLogger("remote_tts_server")

AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".ogg"}
PIPER_QUALITY_SUFFIXES = {"x_low", "low", "medium", "high", "x_high"}


def contains_segment(path: Path, segment: str) -> bool:
    target = segment.lower()
    return any(part.lower() == target for part in path.parts)


def voice_id_from_model_path(model_path: Path) -> str:
    lower_name = model_path.name.lower()
    if lower_name.endswith(".onnx.gz"):
        return model_path.name[:-8]
    if lower_name.endswith(".onnx"):
        return model_path.stem
    return model_path.stem


class VoiceCatalog:
    def __init__(self, piper_root: Path, xtts_root: Path) -> None:
        self.piper_root = piper_root
        self.xtts_root = xtts_root
        self._lock = RLock()
        self._piper_voices: List[PiperVoice] = []
        self._xtts_sources: List[XttsSourceVoice] = []

    @staticmethod
    def _parse_piper_language(stem: str) -> str:
        first = stem.split("-", 1)[0]
        if re.match(r"^[a-z]{2}_[A-Z]{2}$", first):
            return first
        return "unknown"

    @staticmethod
    def _parse_piper_quality(stem: str) -> Optional[str]:
        last = stem.split("-")[-1].lower()
        return last if last in PIPER_QUALITY_SUFFIXES else None

    def refresh(self) -> Dict[str, int]:
        piper_voices: List[PiperVoice] = []
        xtts_sources: List[XttsSourceVoice] = []

        if self.piper_root.exists():
            for file_path in self.piper_root.rglob("*"):
                if not file_path.is_file():
                    continue
                if contains_segment(file_path, "piper-env"):
                    continue
                name = file_path.name.lower()
                if not (name.endswith(".onnx") or name.endswith(".onnx.gz")):
                    continue

                voice_id = voice_id_from_model_path(file_path)
                language = self._parse_piper_language(voice_id)
                quality = self._parse_piper_quality(voice_id)
                config_path = Path(str(file_path) + ".json")

                piper_voices.append(
                    PiperVoice(
                        voice_id=voice_id,
                        language=language,
                        quality=quality,
                        model_path=str(file_path),
                        config_path=str(config_path) if config_path.exists() else None,
                    )
                )

        if self.xtts_root.exists():
            for file_path in self.xtts_root.rglob("*"):
                if not file_path.is_file():
                    continue
                if contains_segment(file_path, "tts_env"):
                    continue
                if file_path.suffix.lower() not in AUDIO_EXTENSIONS:
                    continue

                xtts_sources.append(
                    XttsSourceVoice(
                        voice_id=file_path.stem,
                        file_path=str(file_path),
                        extension=file_path.suffix.lower(),
                    )
                )

        piper_voices.sort(key=lambda item: (item.language, item.voice_id))
        xtts_sources.sort(key=lambda item: item.voice_id)

        with self._lock:
            self._piper_voices = piper_voices
            self._xtts_sources = xtts_sources

        logger.info(
            "Voice catalog refreshed | piper=%d | xtts_sources=%d",
            len(piper_voices),
            len(xtts_sources),
        )
        return {"piper": len(piper_voices), "xtts_sources": len(xtts_sources)}

    def get_piper_voices(self) -> List[PiperVoice]:
        with self._lock:
            return list(self._piper_voices)

    def get_xtts_sources(self) -> List[XttsSourceVoice]:
        with self._lock:
            return list(self._xtts_sources)

    def resolve_piper_voice(self, language: Optional[str], piper_opts: Dict[str, Any]) -> PiperVoice:
        voices = self.get_piper_voices()
        if not voices:
            raise HTTPException(status_code=500, detail="No Piper model found. Run refresh and verify piper root.")

        requested_model_path = str(piper_opts.get("model_path", "")).strip()
        if requested_model_path:
            custom_model = Path(requested_model_path)
            if not custom_model.is_absolute():
                custom_model = self.piper_root / custom_model
            if not custom_model.exists():
                raise HTTPException(status_code=400, detail=f"Piper model_path not found: {custom_model}")
            config_path = Path(str(custom_model) + ".json")
            voice_id = voice_id_from_model_path(custom_model)
            return PiperVoice(
                voice_id=voice_id,
                language=self._parse_piper_language(voice_id),
                quality=self._parse_piper_quality(voice_id),
                model_path=str(custom_model),
                config_path=str(config_path) if config_path.exists() else None,
            )

        requested_voice = str(piper_opts.get("voice_id") or piper_opts.get("voice") or "").strip().lower()
        if requested_voice:
            for voice in voices:
                if voice.voice_id.lower() == requested_voice:
                    return voice
            raise HTTPException(status_code=400, detail=f"Unknown Piper voice_id: {requested_voice}")

        requested_language = str(language or piper_opts.get("language") or "").strip().lower()
        requested_quality = str(piper_opts.get("quality") or "medium").strip().lower()
        if requested_language:
            lang_voices = [voice for voice in voices if voice.language.lower() == requested_language]
            if lang_voices:
                for voice in lang_voices:
                    if (voice.quality or "").lower() == requested_quality:
                        return voice
                return lang_voices[0]

        return voices[0]

    def resolve_xtts_source(self, explicit_speaker: Optional[str], xtts_opts: Dict[str, Any]) -> Optional[str]:
        requested = str(explicit_speaker or xtts_opts.get("speaker_wav") or "").strip()
        if requested:
            candidate = Path(requested)
            if not candidate.is_absolute():
                candidate = self.xtts_root / requested
            if candidate.exists() and candidate.is_file():
                return str(candidate)

            req_lower = requested.lower()
            for source in self.get_xtts_sources():
                if source.voice_id.lower() == req_lower:
                    return source.file_path
            raise HTTPException(status_code=400, detail=f"Unknown XTTS speaker_wav or voice_id: {requested}")

        sources = self.get_xtts_sources()
        if not sources:
            return None
        return sources[0].file_path
