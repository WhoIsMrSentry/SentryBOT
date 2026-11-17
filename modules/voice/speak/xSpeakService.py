from __future__ import annotations

import argparse
import logging
import re
import threading
import time
from typing import Any, Dict, Optional

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore

from fastapi import FastAPI

from modules.common.bind_host import apply_bind_host
from modules.common.latency_trace import latency_trace
from modules.voice.speak.config_loader import load_config
from modules.voice.speak.services.player import AudioPlayer
from modules.voice.speak.services.speech_queue import SpeechPriorityQueue
from modules.voice.speak.services.tts import TextToSpeech, TTSUnavailableError

try:
    from modules.common.logger import init_logging as _init_global_logging  # type: ignore

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
    "anger": {"rate": 210, "volume": 1.0},
    "angry": {"rate": 210, "volume": 1.0},
    "frustrated": {"rate": 165, "volume": 0.9},
    "frustration": {"rate": 165, "volume": 0.9},
    "surprise": {"rate": 195, "volume": 1.0},
    "surprised": {"rate": 195, "volume": 1.0},
    "gentle": {"rate": 150, "volume": 0.8},
    "love": {"rate": 150, "volume": 0.8},
    "disgusted": {"rate": 160, "volume": 0.9},
    "disgust": {"rate": 160, "volume": 0.9},
    "confused": {"rate": 165, "volume": 0.9},
    "confusion": {"rate": 165, "volume": 0.9},
    "worried": {"rate": 175, "volume": 0.9},
    "bored": {"rate": 140, "volume": 0.7},
    "proud": {"rate": 180, "volume": 0.95},
    "embarrassed": {"rate": 155, "volume": 0.75},
    "awe": {"rate": 165, "volume": 0.9},
    "suspicious": {"rate": 150, "volume": 0.85},
    "safety": {"rate": 205, "volume": 1.0},
}


class SpeakService:
    def __init__(self, config_path: Optional[str] = None) -> None:
        self.cfg = load_config(config_path)
        self.tts = TextToSpeech(self.cfg.get("tts", {}))
        self.player = AudioPlayer(self.cfg.get("audio_out", {}))
        self._liveliness_cfg = self.cfg.get("liveliness", {}) or {}
        # R21: separate serialization for synthesis (model access) vs playback
        # (single speaker). _speech_lock kept as alias for compatibility.
        self._synth_lock = threading.RLock()
        self._play_lock = threading.RLock()
        self._speech_lock = self._synth_lock
        self._is_speaking = False
        self._playback_listeners: list = []
        self._playback_listeners_lock = threading.Lock()
        self._expr_session: Any = None
        tts_cfg = self.cfg.get("tts", {}) if isinstance(self.cfg.get("tts"), dict) else {}
        self.stream_max_chunk_chars = max(40, int(tts_cfg.get("stream_max_chunk_chars", 180)))
        self.priority_queue = SpeechPriorityQueue(stop_callback=self.stop)

    def register_playback_listener(self, callback: Any) -> None:
        """Register a listener ``cb(active: bool, estimated_rms: float)`` for TTS playback."""
        if not callable(callback):
            return
        lock = getattr(self, "_playback_listeners_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._playback_listeners_lock = lock
        with lock:
            listeners = getattr(self, "_playback_listeners", None)
            if listeners is None:
                listeners = []
                self._playback_listeners = listeners
            if callback not in listeners:
                listeners.append(callback)

    def _notify_playback_listeners(self, active: bool, estimated_rms: float = 1200.0) -> None:
        listeners = getattr(self, "_playback_listeners", None)
        if not listeners:
            return
        lock = getattr(self, "_playback_listeners_lock", None)
        if lock is not None:
            with lock:
                snapshot = list(listeners)
        else:
            snapshot = list(listeners)
        for cb in snapshot:
            try:
                cb(bool(active), float(estimated_rms))
            except Exception as exc:
                logger.debug("playback listener error: %s", exc)

    @property
    def is_speaking(self) -> bool:
        return bool(self._is_speaking)

    def stop(self) -> None:
        """Stop synthesis and playback immediately (0ms barge-in)."""
        self._is_speaking = False
        try:
            from modules.voice.speak.services.tts import cancel_synthesis

            cancel_synthesis()
        except Exception:
            pass
        self.player.stop_playback()
        self._notify_playback_listeners(False, 0.0)

    def set_stream_max_chunk_chars(self, value: int) -> Dict[str, Any]:
        self.stream_max_chunk_chars = max(40, int(value))
        return {"ok": True, "max_chunk_chars": self.stream_max_chunk_chars}

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
        try:
            from modules.ai_provider.services.tags import strip_speech_control_artifacts

            raw = strip_speech_control_artifacts(raw)
        except Exception:
            pass
        if not raw:
            return ""
        raw = re.sub(r"```.*?```", " ", raw, flags=re.DOTALL)
        raw = re.sub(r"`([^`]*)`", r"\1", raw)
        raw = re.sub(r"\[(düşünce|thinking|iç ses|reasoning|gerekçe).*?\]", " ", raw, flags=re.IGNORECASE)
        clean: list[str] = []
        thought_re = re.compile(
            r"^(analysis|reasoning|thinking|internal state|tool_call|düşünce|dusunce|iç ses|ic ses|düşünüyorum|gerekçe|gerekce|analiz|iç durum|ic durum|plan|araç çağrısı|arac cagrisi)\s*:",
            re.IGNORECASE,
        )
        for line in raw.splitlines():
            value = line.strip()
            if not value or re.match(r"^[#>*•-]\s*", value):
                continue
            norm_val = value.replace("İ", "i").replace("I", "ı")
            if thought_re.match(norm_val):
                continue
            clean.append(value.replace("*", ""))
        return re.sub(r"\s+", " ", " ".join(clean)).strip()

    def _resolve_expression_url(self, raw_base: str) -> str:
        base = str(raw_base or "").strip().rstrip("/")
        if not base:
            return ""
        if base.startswith("@gateway"):
            suffix = base[len("@gateway") :].lstrip("/")
            try:
                from modules.gateway.url import gateway_url, resolve_gateway_base_url

                return gateway_url(resolve_gateway_base_url(self.cfg), f"/{suffix}").rstrip("/")
            except Exception:
                return f"http://127.0.0.1:8080/{suffix}".rstrip("/")
        return base

    def _expression_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        if requests is None or not bool(self._liveliness_cfg.get("enabled", True)):
            return
        base = self._resolve_expression_url(self._liveliness_cfg.get("expression_base_url", ""))
        if not base:
            return
        timeout_s = float(self._liveliness_cfg.get("event_timeout_s", 0.35))
        payload = {"type": event_type, "data": dict(data or {})}

        def _send() -> None:
            try:
                url = f"{base}/event"
                post_fn = getattr(requests, "post", None)
                if getattr(post_fn, "__module__", "") == "requests.api":
                    sess = getattr(self, "_expr_session", None)
                    if sess is None:
                        sess = requests.Session()
                        self._expr_session = sess
                    sess.post(url, json=payload, timeout=timeout_s)
                else:
                    requests.post(url, json=payload, timeout=timeout_s)
            except Exception as exc:
                logger.debug("expression event failed (%s): %s", event_type, exc)

        threading.Thread(target=_send, daemon=True).start()

    def stop_speaking(self) -> Dict[str, Any]:
        q = getattr(self, "priority_queue", None)
        if q is not None:
            q.clear()
        self.stop()
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
        # Split locks (R21): synthesis and playback no longer serialize each
        # other. A second say() can synthesize while the first one plays and
        # only queues at the single speaker resource.
        pcm = None
        with self._synth_lock:
            self._is_speaking = True
            try:
                from modules.voice.speak.services.tts import clear_synthesis_cancel

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
                self._is_speaking = False
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
                self._is_speaking = False
                latency_trace.finish(trace_id, "tts_failed", {"detail": repr(exc)})
                raise

        self._expression_event(
            "speak.started",
            {"trace_id": trace_id, "tone": tone if isinstance(tone, str) else "", "chars": len(cleaned_text)},
        )
        latency_trace.mark(trace_id, "audio.play_start")
        self._notify_playback_listeners(True, 1200.0)
        try:
            with self._play_lock:
                duration_sec = self.player.play_blocking(pcm)
        finally:
            self._is_speaking = False
            self._notify_playback_listeners(False, 0.0)
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
        self._notify_playback_listeners(True, 1200.0)
        try:
            duration_sec = self.player.play_wav_bytes(data)
        finally:
            self._notify_playback_listeners(False, 0.0)
            latency_trace.mark(trace_id, "audio.play_done")
            self._expression_event("speak.finished", {"trace_id": trace_id})
        latency_trace.finish(trace_id, "done", {"duration_sec": duration_sec})
        return {"ok": True, "trace_id": trace_id, "duration_sec": duration_sec}


def create_app(config_path: str | None = None) -> FastAPI:
    service = SpeakService(config_path)
    app = FastAPI()
    from modules.voice.speak.api import get_router

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

        cfg = apply_bind_host(load_config(args.config), "SPEAK_HOST")
        server = cfg.get("server", {})
        uvicorn.run(
            create_app(args.config),
            host=str(server.get("host", "127.0.0.1")),
            port=int(server.get("port", 8083)),
            log_config=None,
        )
        return

    print(SpeakService(args.config).speak(" ".join(args.text)))


if __name__ == "__main__":
    main()
