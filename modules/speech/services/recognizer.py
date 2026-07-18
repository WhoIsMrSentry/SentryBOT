from __future__ import annotations
import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, Optional
from pathlib import Path

# Lazy-loaded native backends. Keep imports deferred to runtime paths to avoid
# importing heavy/native libs during plain module import and smoke tests.
webrtcvad = None  # type: ignore
Model = None  # type: ignore
KaldiRecognizer = None  # type: ignore

logger = logging.getLogger("speech.recognizer")


@dataclass
class RecognitionResult:
    text: str
    is_final: bool
    confidence: Optional[float] = None


@dataclass
class RecognizerConfig:
    # language or model_path can be provided. model_path takes precedence.
    language: Optional[str] = None
    model_path: Optional[str] = None
    language_models: Dict[str, str] | None = None
    samplerate: int = 16000
    max_alternatives: int = 0
    vad_enabled: bool = False
    vad_aggressiveness: int = 2
    vad_hangover_ms: int = 300


class Recognizer:
    def __init__(self, cfg: Dict):
        self.cfg = RecognizerConfig(
            language=cfg.get("language"),
            model_path=cfg.get("model_path"),
            language_models=cfg.get("language_models"),
            samplerate=int(cfg.get("samplerate", 16000)),
            max_alternatives=int(cfg.get("max_alternatives", 0)),
            vad_enabled=bool(cfg.get("vad", {}).get("enabled", False)),
            vad_aggressiveness=int(cfg.get("vad", {}).get("aggressiveness", 2)),
            vad_hangover_ms=int(cfg.get("vad", {}).get("hangover_ms", 300)),
        )
        self._model = None
        self._rec = None
        self._vad = None
        # Resolve model path relative to module root when not absolute (if provided)
        if self.cfg.model_path and not os.path.isabs(self.cfg.model_path):
            module_root = Path(__file__).resolve().parents[1]  # .../modules/speech
            resolved = module_root / self.cfg.model_path
            self.cfg.model_path = str(resolved)

    def _resolve_model_path(self) -> str:
        if self.cfg.model_path:
            return str(self.cfg.model_path)
        lang = (self.cfg.language or "tr").lower()
        mapping = self.cfg.language_models or {
            "tr": "models/vosk-tr",
            "en": "models/vosk-en",
            "en-us": "models/vosk-en-us",
            "de": "models/vosk-de",
            "es": "models/vosk-es",
            "fr": "models/vosk-fr",
        }
        return mapping.get(lang, mapping.get("en", "models/vosk-en"))

    def resolved_model_path(self) -> str:
        """Return the absolute model path that this recognizer would load."""
        model_path = self._resolve_model_path()
        if not os.path.isabs(model_path):
            module_root = Path(__file__).resolve().parents[1]
            model_path = str((module_root / model_path).resolve())
        return str(model_path)

    def status(self) -> dict:
        """Cheap readiness check; never loads the heavy Vosk model."""
        model_path = self.resolved_model_path()
        vosk_available = True
        vosk_error = ""
        try:
            import vosk  # type: ignore  # noqa: F401
        except Exception as exc:
            vosk_available = False
            vosk_error = str(exc)
        model_exists = os.path.isdir(model_path)
        error_parts = []
        if not vosk_available:
            error_parts.append("vosk package unavailable")
        if not model_exists:
            error_parts.append("model directory missing")
        return {
            "ok": bool(vosk_available and model_exists),
            "language": self.cfg.language or "tr",
            "model_path": model_path,
            "model_exists": bool(model_exists),
            "model_loaded": bool(self._model is not None),
            "vosk_available": bool(vosk_available),
            "vosk_error": vosk_error,
            "error": "; ".join(error_parts),
        }

    def is_available(self) -> bool:
        return bool(self.status().get("ok"))

    def _ensure_model(self):
        global Model, KaldiRecognizer, webrtcvad
        if Model is None or KaldiRecognizer is None:
            try:
                from vosk import Model as _Model, KaldiRecognizer as _KaldiRecognizer  # type: ignore
            except Exception as exc:
                raise RuntimeError(
                    "vosk is not available. Install with 'pip install vosk' and download an offline model."
                ) from exc
            Model = _Model
            KaldiRecognizer = _KaldiRecognizer
        if self._model is None:
            model_path = self.resolved_model_path()
            if not os.path.isdir(model_path):
                raise FileNotFoundError(f"Vosk model directory not found: {model_path}")
            self._model = Model(model_path)
        if self._rec is None:
            self._rec = KaldiRecognizer(self._model, self.cfg.samplerate)
            if self.cfg.max_alternatives:
                self._rec.SetMaxAlternatives(self.cfg.max_alternatives)
        if self.cfg.vad_enabled:
            if webrtcvad is None:
                try:
                    import webrtcvad as _webrtcvad  # type: ignore
                except Exception as exc:
                    logger.warning(
                        "webrtcvad unavailable; continuing without VAD (%s). "
                        "Install with 'pip install webrtcvad' for VAD filtering.",
                        exc,
                    )
                    self.cfg.vad_enabled = False
                else:
                    webrtcvad = _webrtcvad
            if self.cfg.vad_enabled and webrtcvad is not None and self._vad is None:
                self._vad = webrtcvad.Vad(self.cfg.vad_aggressiveness)

    def run(self, stream: Iterable[bytes]) -> Iterator[RecognitionResult]:
        self._ensure_model()
        hangover_frames = 0
        # 20ms step size for VAD, samples->bytes: int16 -> *2
        vad_step_bytes = int(self.cfg.samplerate * 0.02) * 2
        for chunk in stream:
            data = chunk
            if self._vad:
                voiced_any = False
                # iterate over 20ms frames
                for i in range(0, len(data), vad_step_bytes):
                    frame = data[i:i + vad_step_bytes]
                    if len(frame) < vad_step_bytes:
                        break
                    try:
                        if self._vad.is_speech(frame, self.cfg.samplerate):
                            voiced_any = True
                            break
                    except Exception:
                        voiced_any = True
                        break
                if not voiced_any:
                    if hangover_frames > 0:
                        hangover_frames -= 1
                    else:
                        continue
                else:
                    # Set hangover to ~vad_hangover_ms/20ms frames
                    hangover_frames = max(hangover_frames, max(1, int(self.cfg.vad_hangover_ms / 20)))

            if self._rec.AcceptWaveform(data):
                res = json.loads(self._rec.Result())
                yield RecognitionResult(text=res.get("text", ""), is_final=True, confidence=res.get("confidence"))
            else:
                partial = json.loads(self._rec.PartialResult()).get("partial", "")
                if partial:
                    yield RecognitionResult(text=partial, is_final=False)

    def finalize(self) -> Optional[RecognitionResult]:
        if self._rec is None:
            return None
        data = json.loads(self._rec.FinalResult())
        text = data.get("text", "")
        conf = data.get("confidence")
        return RecognitionResult(text=text, is_final=True, confidence=conf)

    def recognize_pcm(self, pcm: bytes) -> str:
        """One-shot decode of a mono PCM16 utterance buffer."""
        if not pcm:
            return ""
        self._ensure_model()
        rec = KaldiRecognizer(self._model, self.cfg.samplerate)
        if self.cfg.max_alternatives:
            rec.SetMaxAlternatives(self.cfg.max_alternatives)
        step = max(4000, int(self.cfg.samplerate * 0.02) * 2)
        for i in range(0, len(pcm), step):
            rec.AcceptWaveform(pcm[i : i + step])
        data = json.loads(rec.FinalResult())
        return str(data.get("text", "") or "").strip()
