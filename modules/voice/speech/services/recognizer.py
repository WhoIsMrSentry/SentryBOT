from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Optional

logger = logging.getLogger("speech.recognizer")

try:
    import speech_recognition as sr
except ImportError:
    sr = None  # type: ignore


@dataclass
class RecognitionResult:
    text: str
    is_final: bool
    confidence: Optional[float] = None


@dataclass
class RecognizerConfig:
    language: str = "tr"
    samplerate: int = 16000
    vad_enabled: bool = False
    vad_aggressiveness: int = 2
    vad_hangover_ms: int = 400
    min_utterance_sec: float = 0.6
    max_utterance_sec: float = 15.0


class Recognizer:
    """SpeechRecognizer using online SpeechRecognition backend."""

    def __init__(self, cfg: Optional[Dict[str, Any]] = None):
        cfg = cfg or {}
        self.cfg = RecognizerConfig(
            language=str(cfg.get("language") or cfg.get("source_language") or "tr"),
            samplerate=int(cfg.get("samplerate", 16000)),
            vad_enabled=bool(cfg.get("vad", {}).get("enabled", False) if isinstance(cfg.get("vad"), dict) else False),
            vad_aggressiveness=int(cfg.get("vad", {}).get("aggressiveness", 2) if isinstance(cfg.get("vad"), dict) else 2),
            vad_hangover_ms=int(cfg.get("vad", {}).get("hangover_ms", 400) if isinstance(cfg.get("vad"), dict) else 400),
        )
        self._sr_recognizer = sr.Recognizer() if sr is not None else None

    def status(self) -> dict[str, Any]:
        """Check speech recognition backend readiness."""
        sr_available = sr is not None
        return {
            "ok": sr_available,
            "engine": "speech_recognition",
            "language": self.cfg.language,
            "sr_available": sr_available,
            "error": "" if sr_available else "speech_recognition package unavailable",
        }

    def is_available(self) -> bool:
        return bool(self.status().get("ok"))

    def _ensure_model(self) -> None:
        if sr is None:
            raise RuntimeError(
                "SpeechRecognition is not available. Install with 'pip install SpeechRecognition'."
            )

    def recognize_pcm(self, pcm: bytes) -> str:
        """Transcribe mono PCM16 utterance buffer."""
        if not pcm or len(pcm) < 1600:
            return ""
        self._ensure_model()
        from modules.voice.speech.services.online_stt import transcribe_google_multilang

        text, _ = transcribe_google_multilang(
            pcm,
            samplerate=self.cfg.samplerate,
            languages=[self.cfg.language, "en"],
            default_lang=self.cfg.language,
        )
        return text

    def run(self, stream: Iterable[bytes]) -> Iterator[RecognitionResult]:
        """Process streaming audio chunks and yield recognition results."""
        self._ensure_model()
        buffer = bytearray()
        bytes_per_sec = self.cfg.samplerate * 2  # 16-bit mono PCM
        min_bytes = int(self.cfg.min_utterance_sec * bytes_per_sec)
        max_bytes = int(self.cfg.max_utterance_sec * bytes_per_sec)
        preroll_bytes = int(0.35 * bytes_per_sec)  # 350ms rolling pre-roll buffer
        silence_threshold = 250  # amplitude threshold
        silence_chunks = 0
        max_silence_chunks = max(8, int(self.cfg.vad_hangover_ms / 30))
        has_spoken = False

        for chunk in stream:
            if not chunk:
                continue

            # Check approximate energy of this audio chunk
            is_silent = True
            if len(chunk) >= 2:
                import numpy as np
                try:
                    samples = np.frombuffer(chunk, dtype=np.int16)
                    energy = np.mean(np.abs(samples))
                    if energy > silence_threshold:
                        is_silent = False
                except Exception:
                    is_silent = False

            if not is_silent:
                has_spoken = True
                silence_chunks = 0
                buffer.extend(chunk)
            else:
                if has_spoken:
                    silence_chunks += 1
                    buffer.extend(chunk)
                else:
                    # Speech has not started yet; keep only the last pre-roll bytes
                    buffer.extend(chunk)
                    if len(buffer) > preroll_bytes:
                        buffer = buffer[-preroll_bytes:]

            # Trigger recognition when silence is detected AFTER speech or buffer reaches maximum length
            should_flush = False
            if has_spoken:
                if len(buffer) >= max_bytes:
                    should_flush = True
                elif len(buffer) >= min_bytes and silence_chunks >= max_silence_chunks:
                    should_flush = True

            if should_flush:
                pcm_data = bytes(buffer)
                buffer.clear()
                has_spoken = False
                silence_chunks = 0
                try:
                    text = self.recognize_pcm(pcm_data)
                    if text:
                        yield RecognitionResult(text=text, is_final=True, confidence=0.9)
                except Exception as exc:
                    logger.debug("recognize_pcm error: %s", exc)

        if has_spoken and len(buffer) >= min_bytes:
            try:
                text = self.recognize_pcm(bytes(buffer))
                if text:
                    yield RecognitionResult(text=text, is_final=True, confidence=0.9)
            except Exception as exc:
                logger.debug("recognize_pcm finalize error: %s", exc)

    def finalize(self) -> Optional[RecognitionResult]:
        return None
