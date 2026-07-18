from __future__ import annotations

import argparse
import logging
import re
import threading
import time
import uuid
from typing import Any, Dict, Optional, TYPE_CHECKING

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore

from fastapi import FastAPI

from modules.common.latency_trace import latency_trace
from modules.speak.config_loader import load_config
from modules.speak.services.player import AudioPlayer
from modules.speak.services.tts import TextToSpeech, TTSUnavailableError

if TYPE_CHECKING:
    from modules.speak.api import get_router  # type: ignore

try:
    from modules.logwrapper import init_logging as _init_global_logging  # type: ignore

    _init_global_logging()
except Exception:
    pass

logger = logging.getLogger("speak")

_TONE_PRESETS: Dict[str, Dict[str, float]] = {
    "neutral": {"rate": 170, "volume": 0.85},
    "joy": {"rate": 190, "volume": 1.0},
    "happy": {"rate": 190, "volume": 1.0},
    "fast": {"rate": 190, "volume": 1.0},
    "calm": {"rate": 160, "volume": 0.72},
    "excited": {"rate": 200, "volume": 1.0},
    "sadness": {"rate": 150, "volume": 0.75},
    "sad": {"rate": 150, "volume": 0.75},
    "curiosity": {"rate": 185, "volume": 0.9},
    "curious": {"rate": 185, "volume": 0.9},
    "tired": {"rate": 140, "volume": 0.65},
    "fear": {"rate": 200, "volume": 0.9},
}


class SpeakService:
    def __init__(self, config_path: Optional[str] = None) -> None:
        self.cfg = load_config(config_path)
        self.tts = TextToSpeech(self.cfg.get("tts", {}))
        self.player = AudioPlayer(self.cfg.get("audio_out", {}))
        self._liveliness_cfg = self.cfg.get("liveliness", {}) or {}
        self._speech_lock = threading.RLock()

    @staticmethod
    def _coerce_tone(tone: Any) -> Optional[Dict[str, Any]]:
        if tone is None:
            return None
        if isinstance(tone, dict):
            return dict(tone)
        if isinstance(tone, str):
            return dict(_TONE_PRESETS.get(tone.strip().lower(), {})) or None
        return None

    @staticmethod
    def _tone_to_piper(tone: Optional[Dict[str, Any]]) -> Optional[Dict[str, float]]:
        if not isinstance(tone, dict):
            return None
        rate = tone.get("rate")
        if not isinstance(rate, (int, float)) or rate <= 0:
            return None
        length_scale = max(0.62, min(1.55, 170.0 / float(rate)))
        noise_w = max(0.45, min(1.05, 0.78 * (float(rate) / 170.0)))
        return {"length_scale": round(length_scale, 3), "noise_w": round(noise_w, 3)}

    @staticmethod
    def _clean_text_for_speech(text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        raw = re.sub(r"```.*?```", " ", raw, flags=re.DOTALL)
        raw = re.sub(r"`([^`]*)`", r"\1", raw)
        clean: list[str] = []
        for line in raw.splitlines():
            value = line.strip()
            if not value or re.match(r"^[#>*•-]\s*", value):
                continue
            low = value.lower()
            if low.startswith(("analysis:", "reasoning:", "thinking:", "internal state:", "tool_call:")):
                continue
            clean.append(value.replace("*", ""))
        return re.sub(r"\s+", " ", " ".join(clean)).strip()

    def _expression_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        if requests is None or not bool(self._liveliness_cfg.get("enabled", True)):
            return
        base = str(self._liveliness_cfg.get("expression_base_url", "")).strip().rstrip("/")
        if not base:
            return
        try:
            requests.post(
                f"{base}/event",
                json={"type": event_type, "data": dict(data or {})},
                timeout=float(self._liveliness_cfg.get("event_timeout_s", 0.35)),
            )
        except Exception:
            logger.debug("expression event failed: %s", event_type, exc_info=True)

    def stop_speaking(self) -> Dict[str, Any]:
        try:
            from modules.speak.services.tts import cancel_synthesis

            cancel_synthesis()
        except Exception:
            pass
        self.player.stop_playback()
        self._expression_event("speak.finished", {"interrupted": True})
        return {"ok": True, "stopped": True}

    def speak(
        self,
        text: str,
        engine: Optional[str] = None,
        tone: Optional[Dict[str, Any]] | str = None,
        speaker_wav: Optional[str] = None,
        language: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not str(text or "").strip():
            raise ValueError("text is empty")

        trace_id = latency_trace.ensure(trace_id, {"component": "speak", "language": language or ""})
        latency_trace.mark(trace_id, "tts.request_received", {"chars": len(str(text))})
        cleaned_text = self._clean_text_for_speech(text)
        if not cleaned_text:
            latency_trace.finish(trace_id, "skipped", {"reason": "empty_after_cleaning"})
            return {"ok": True, "trace_id": trace_id, "duration_sec": 0.0, "skipped": True}

        tone_dict = self._coerce_tone(tone)
        overrides: Dict[str, Any] = dict(tone_dict or {})
        if engine:
            overrides["engine"] = engine
        if speaker_wav:
            overrides["speaker_wav"] = speaker_wav
        if language:
            overrides["language"] = language

        active_engine = str(engine or self.cfg.get("tts", {}).get("engine", "piper")).strip().lower()
        if active_engine == "piper":
            piper_tone = self._tone_to_piper(tone_dict)
            if piper_tone:
                overrides["piper"] = piper_tone

        used_engine = overrides.get("engine") or self.cfg.get("tts", {}).get("engine")
        with self._speech_lock:
            try:
                from modules.speak.services.tts import clear_synthesis_cancel

                clear_synthesis_cancel()
                synth_started = time.monotonic()
                latency_trace.mark(trace_id, "tts.synthesis_start", {"engine": used_engine})
                pcm = self.tts.synthesize(cleaned_text, overrides=overrides or None)
                synthesis_ms = round((time.monotonic() - synth_started) * 1000.0, 2)
                latency_trace.mark(
                    trace_id,
                    "tts.synthesis_done",
                    {"engine": used_engine, "duration_ms": synthesis_ms, "samplerate": pcm.samplerate},
                )
            except TTSUnavailableError as exc:
                latency_trace.finish(trace_id, "tts_unavailable", {"detail": str(exc)})
                logger.warning("speech skipped: %s", exc)
                return {
                    "ok": False,
                    "trace_id": trace_id,
                    "engine": used_engine,
                    "error": "tts_unavailable",
                    "detail": str(exc),
                    "duration_sec": 0.0,
                }
            except Exception as exc:
                latency_trace.finish(trace_id, "tts_failed", {"detail": repr(exc)})
                raise

            self._expression_event(
                "speak.started",
                {"trace_id": trace_id, "tone": tone if isinstance(tone, str) else "", "chars": len(cleaned_text)},
            )
            latency_trace.mark(trace_id, "audio.play_start")
            try:
                duration_sec = self.player.play_blocking(pcm)
            finally:
                latency_trace.mark(trace_id, "audio.play_done")
                self._expression_event("speak.finished", {"trace_id": trace_id})

        latency_trace.finish(trace_id, "done", {"duration_sec": duration_sec})
        snapshot = latency_trace.get(trace_id) or {}
        return {
            "ok": True,
            "trace_id": trace_id,
            "engine": used_engine,
            "duration_sec": duration_sec,
            "samplerate": pcm.samplerate,
            "latency_ms": snapshot.get("elapsed_ms", 0.0),
        }

    def play_wav(self, data: bytes, trace_id: Optional[str] = None) -> Dict[str, Any]:
        trace_id = latency_trace.ensure(trace_id, {"component": "speak.play_wav"})
        self._expression_event("speak.started", {"trace_id": trace_id})
        latency_trace.mark(trace_id, "audio.play_start")
        try:
            duration_sec = self.player.play_wav_bytes(data)
        finally:
            latency_trace.mark(trace_id, "audio.play_done")
            self._expression_event("speak.finished", {"trace_id": trace_id})
        latency_trace.finish(trace_id, "done", {"duration_sec": duration_sec})
        return {"ok": True, "trace_id": trace_id, "duration_sec": duration_sec}


def create_app(config_path: str | None = None) -> FastAPI:
    service = SpeakService(config_path)
    app = FastAPI()
    from modules.speak.api import get_router

    app.include_router(get_router(service))
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Speech output service")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--api", action="store_true")
    parser.add_argument("text", nargs="*")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    if args.api or not args.text:
        import uvicorn  # type: ignore

        cfg = load_config(args.config)
        server = cfg.get("server", {})
        uvicorn.run(
            create_app(args.config),
            host=str(server.get("host", "0.0.0.0")),
            port=int(server.get("port", 8083)),
            log_config=None,
        )
        return

    print(SpeakService(args.config).speak(" ".join(args.text)))


if __name__ == "__main__":
    main()
