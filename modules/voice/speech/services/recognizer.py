from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Iterator, Optional

from modules.voice.speech.services.turn_taking import DynamicTurnTakingEngine

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
    language: Optional[str] = None


@dataclass
class RecognizerConfig:
    language: str = "tr"
    samplerate: int = 16000
    channels: int = 1
    vad_enabled: bool = False
    vad_aggressiveness: int = 2
    vad_hangover_ms: int = 400
    min_utterance_sec: float = 0.5
    max_utterance_sec: float = 15.0
    silence_threshold: float = 75.0
    dual_decode_languages: tuple[str, ...] = ("tr", "en")


class Recognizer:
    """SpeechRecognizer using online SpeechRecognition backend + DynamicTurnTakingEngine."""

    def __init__(
        self,
        cfg: Optional[Dict[str, Any]] = None,
        *,
        on_turn_cue: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        cfg = cfg or {}
        vad_cfg = cfg.get("vad", {}) if isinstance(cfg.get("vad"), dict) else {}
        dual_langs = cfg.get("dual_decode_languages")
        if isinstance(dual_langs, (list, tuple)) and dual_langs:
            lang_tuple = tuple(str(l).split("-", 1)[0].lower() for l in dual_langs if str(l).strip())
        else:
            lang_tuple = ("tr", "en")

        self.cfg = RecognizerConfig(
            language=str(cfg.get("language") or cfg.get("source_language") or "tr"),
            samplerate=int(cfg.get("samplerate", 16000)),
            channels=max(1, int(cfg.get("channels", 1))),
            vad_enabled=bool(vad_cfg.get("enabled", False)),
            vad_aggressiveness=int(vad_cfg.get("aggressiveness", 2)),
            vad_hangover_ms=int(vad_cfg.get("hangover_ms", 400)),
            min_utterance_sec=float(cfg.get("min_utterance_sec", 0.5)),
            max_utterance_sec=float(cfg.get("max_utterance_sec", 15.0)),
            silence_threshold=float(cfg.get("silence_threshold", 75.0)),
            dual_decode_languages=lang_tuple,
        )
        self._sr_recognizer = sr.Recognizer() if sr is not None else None
        self._on_turn_cue = on_turn_cue
        self._turn_engine = DynamicTurnTakingEngine(
            min_speech_duration_s=max(0.25, self.cfg.min_utterance_sec * 0.7),
            end_of_turn_silence_s=max(0.35, self.cfg.vad_hangover_ms / 1000.0),
            max_turn_timeout_s=max(2.0, self.cfg.max_utterance_sec),
        )

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

    def recognize_pcm(self, pcm: bytes) -> tuple[str, str]:
        """Transcribe mono PCM16 utterance buffer. Returns (text, lang)."""
        if not pcm or len(pcm) < 1600:
            return "", self.cfg.language
        self._ensure_model()
        from modules.voice.speech.services.online_stt import transcribe_google_multilang

        langs = [self.cfg.language] + [l for l in self.cfg.dual_decode_languages if l != self.cfg.language]
        text, lang = transcribe_google_multilang(
            pcm,
            samplerate=self.cfg.samplerate,
            languages=langs,
            default_lang=self.cfg.language,
        )
        return text, lang

    def run(self, stream: Iterable[bytes]) -> Iterator[RecognitionResult]:
        """Process streaming audio chunks and yield recognition results."""
        self._ensure_model()
        import numpy as np

        buffer = bytearray()
        bytes_per_sec = max(1, self.cfg.samplerate * 2)  # 16-bit mono PCM
        min_bytes = int(self.cfg.min_utterance_sec * bytes_per_sec)
        max_bytes = int(self.cfg.max_utterance_sec * bytes_per_sec)
        preroll_bytes = int(0.35 * bytes_per_sec)  # 350ms rolling pre-roll buffer
        silence_threshold = float(getattr(self.cfg, "silence_threshold", 75.0) or 75.0)
        has_spoken = False
        audio_clock = 0.0
        self._turn_engine.start_listening(current_time_s=audio_clock)

        for chunk in stream:
            if not chunk:
                continue

            mono_chunk = chunk
            energy = 0.0
            if len(chunk) >= 2:
                try:
                    samples = np.frombuffer(chunk, dtype=np.int16)
                    if len(samples) > 0:
                        if self.cfg.channels == 2 and len(samples) % 2 == 0:
                            stereo = samples.reshape(-1, 2)
                            mono_samples = stereo.mean(axis=1).astype(np.int16)
                            mono_chunk = mono_samples.tobytes()
                            energy = float(np.mean(np.abs(mono_samples)))
                        else:
                            energy = float(np.mean(np.abs(samples)))
                except Exception:
                    pass

            chunk_dt = len(mono_chunk) / float(bytes_per_sec)
            audio_clock += max(0.005, chunk_dt)
            is_speech = energy > silence_threshold

            turn_res = self._turn_engine.process_vad_frame(
                is_speech=is_speech,
                current_time_s=audio_clock,
                energy_rms=energy,
            )
            if turn_res.get("suggested_cue") and self._on_turn_cue is not None:
                try:
                    self._on_turn_cue(turn_res)
                except Exception:
                    pass

            if is_speech:
                has_spoken = True
                buffer.extend(mono_chunk)
            elif has_spoken:
                buffer.extend(mono_chunk)
            else:
                buffer.extend(mono_chunk)
                if len(buffer) > preroll_bytes:
                    buffer = buffer[-preroll_bytes:]

            should_flush = False
            if has_spoken:
                if len(buffer) >= max_bytes:
                    should_flush = True
                elif turn_res.get("turn_completed") and len(buffer) >= min_bytes:
                    should_flush = True

            if should_flush:
                pcm_data = bytes(buffer)
                buffer.clear()
                has_spoken = False
                self._turn_engine.start_listening(current_time_s=audio_clock)
                try:
                    logger.info(
                        "Transcribing captured speech (%d bytes, ~%.1fs)...",
                        len(pcm_data),
                        len(pcm_data) / bytes_per_sec,
                    )
                    text, lang = self.recognize_pcm(pcm_data)
                    if text:
                        logger.info("Speech recognised: %r (lang=%s)", text, lang)
                        yield RecognitionResult(text=text, is_final=True, confidence=0.9, language=lang)
                    else:
                        logger.debug("Speech recognition returned empty text")
                except Exception as exc:
                    logger.debug("recognize_pcm error: %s", exc)

        if has_spoken and len(buffer) >= min_bytes:
            try:
                pcm_data = bytes(buffer)
                logger.info("Finalizing speech buffer (%d bytes)...", len(pcm_data))
                text, lang = self.recognize_pcm(pcm_data)
                if text:
                    logger.info("Speech recognised (final): %r (lang=%s)", text, lang)
                    yield RecognitionResult(text=text, is_final=True, confidence=0.9, language=lang)
            except Exception as exc:
                logger.debug("recognize_pcm finalize error: %s", exc)

    def finalize(self) -> Optional[RecognitionResult]:
        return None
