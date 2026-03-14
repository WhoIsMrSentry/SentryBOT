from __future__ import annotations
import argparse
import logging
import re
from typing import Optional

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore

from modules.speak.config_loader import load_config
from modules.speak.services.tts import TextToSpeech
from modules.speak.services.player import AudioPlayer
from fastapi import FastAPI
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.speak.api import get_router  # type: ignore

try:
    from modules.logwrapper import init_logging as _init_global_logging  # type: ignore
    _init_global_logging()
except Exception:
    pass

logger = logging.getLogger("speak")


class SpeakService:
    """Metni sese dönüştürüp MAX98357A üzerinden çalar."""

    def __init__(self, config_path: Optional[str] = None):
        self.cfg = load_config(config_path)
        self.tts = TextToSpeech(self.cfg.get("tts", {}))
        self.player = AudioPlayer(self.cfg.get("audio_out", {}))
        self._liveliness_cfg = self.cfg.get("liveliness", {}) or {}

    def _post_interactions(self, endpoint: str, payload: dict) -> None:
        if requests is None:
            return
        base = str(self._liveliness_cfg.get("interactions_base_url", "")).strip().rstrip("/")
        if not base:
            return
        try:
            requests.post(f"{base}{endpoint}", json=payload, timeout=0.5)
        except Exception:
            pass

    def _estimate_effect_duration_ms(self, text: str, tone: Optional[dict]) -> int:
        cfg = (self._liveliness_cfg.get("speech_effect") or {}) if isinstance(self._liveliness_cfg, dict) else {}
        cps = float(cfg.get("chars_per_second", 16.0))
        min_ms = int(cfg.get("min_duration_ms", 400))
        max_ms = int(cfg.get("max_duration_ms", 7000))
        text_len = max(1, len((text or "").strip()))
        duration_ms = int((text_len / max(1.0, cps)) * 1000.0)
        if tone and isinstance(tone, dict):
            rate = tone.get("rate")
            if isinstance(rate, (int, float)) and rate > 0:
                # 170 ~= neutral baseline in this project.
                duration_ms = int(duration_ms * (170.0 / float(rate)))
        return max(min_ms, min(max_ms, duration_ms))

    @staticmethod
    def _resolve_tone_key(tone: Optional[dict]) -> str:
        if not isinstance(tone, dict):
            return "neutral"
        rate = tone.get("rate")
        volume = tone.get("volume")
        if isinstance(rate, (int, float)):
            if rate >= 190:
                return "fast"
            if rate <= 145:
                return "tired"
        if isinstance(volume, (int, float)) and float(volume) <= 0.7:
            return "calm"
        return "neutral"

    def _resolve_effect_name_for_tone(self, tone: Optional[dict]) -> str:
        cfg = self._liveliness_cfg.get("speech_effect", {}) or {}
        tone_map = cfg.get("tone_effect_map", {}) if isinstance(cfg.get("tone_effect_map", {}), dict) else {}
        key = self._resolve_tone_key(tone)
        return str(tone_map.get(key, cfg.get("name", "PULSE")))

    def _emit_speech_liveliness_start(self, text: str, tone: Optional[dict]) -> None:
        if not bool(self._liveliness_cfg.get("enabled", False)):
            return
        tone_key = self._resolve_tone_key(tone)
        exclamations = str(text or "").count("!")
        questions = str(text or "").count("?")
        self._post_interactions(
            "/event",
            {
                "type": "speech.start",
                "data": {
                    "text_len": len(text or ""),
                    "tone_key": tone_key,
                    "exclamations": exclamations,
                    "questions": questions,
                },
            },
        )
        effect_cfg = self._liveliness_cfg.get("speech_effect", {}) or {}
        effect_name = self._resolve_effect_name_for_tone(tone)
        duration_ms = self._estimate_effect_duration_ms(text, tone)
        force = bool(effect_cfg.get("force", False))
        self._post_interactions(
            "/effect",
            {"name": effect_name, "duration_ms": duration_ms, "force": force},
        )
        self._emit_speech_rhythm_beats(text, force=force)
        emph_map = effect_cfg.get("emphasis_effect_map", {}) if isinstance(effect_cfg.get("emphasis_effect_map", {}), dict) else {}
        if exclamations > 0:
            name = str(emph_map.get("exclamation", "COMET"))
            self._post_interactions("/effect", {"name": name, "duration_ms": 260, "force": force})
        if questions > 0:
            name = str(emph_map.get("question", "TWINKLE"))
            self._post_interactions("/effect", {"name": name, "duration_ms": 240, "force": force})

    def _emit_speech_rhythm_beats(self, text: str, force: bool = False) -> None:
        effect_cfg = self._liveliness_cfg.get("speech_effect", {}) or {}
        rhythm = effect_cfg.get("rhythm", {}) if isinstance(effect_cfg.get("rhythm", {}), dict) else {}
        if not bool(rhythm.get("enabled", False)):
            return
        raw_text = str(text or "")
        words = len([w for w in raw_text.split() if w.strip()])
        clauses = max(1, len([p for p in re.split(r"[,;:.!?]+", raw_text) if p.strip()]))
        if words <= 0 and clauses <= 0:
            return

        mode = str(rhythm.get("mode", "words")).strip().lower()
        words_per_beat = max(1, int(rhythm.get("words_per_beat", 3)))
        clauses_per_beat = max(1, int(rhythm.get("clauses_per_beat", 1)))
        max_beats = max(0, int(rhythm.get("max_beats", 4)))
        if mode == "clauses":
            beat_count = min(max_beats, max(0, clauses // clauses_per_beat))
        else:
            beat_count = min(max_beats, max(0, words // words_per_beat))
        if beat_count <= 0:
            return
        beat_name = str(rhythm.get("effect", "PULSE"))
        beat_duration_ms = max(80, int(rhythm.get("duration_ms", 160)))
        for _ in range(beat_count):
            self._post_interactions("/effect", {"name": beat_name, "duration_ms": beat_duration_ms, "force": force})

        pause_map = rhythm.get("pause_effect_map", {}) if isinstance(rhythm.get("pause_effect_map", {}), dict) else {}
        if not pause_map:
            return
        max_pause_marks = max(0, int(rhythm.get("max_pause_marks", 4)))
        if max_pause_marks <= 0:
            return
        punctuation_counts = {
            ",": raw_text.count(","),
            ";": raw_text.count(";"),
            ":": raw_text.count(":"),
            ".": raw_text.count("."),
        }
        used = 0
        for mark, count in punctuation_counts.items():
            if count <= 0:
                continue
            effect_name = str(pause_map.get(mark, "")).strip()
            if not effect_name:
                continue
            emit_count = min(count, max_pause_marks - used)
            if emit_count <= 0:
                break
            for _ in range(emit_count):
                self._post_interactions(
                    "/effect",
                    {"name": effect_name, "duration_ms": max(80, beat_duration_ms - 30), "force": force},
                )
            used += emit_count
            if used >= max_pause_marks:
                break

    def _emit_speech_liveliness_end(self, duration_sec: float) -> None:
        if not bool(self._liveliness_cfg.get("enabled", False)):
            return
        self._post_interactions("/event", {"type": "speech.end", "data": {"duration_sec": duration_sec}})

    def speak(
        self,
        text: str,
        engine: Optional[str] = None,
        tone: Optional[dict] = None,
        speaker_wav: Optional[str] = None,
        language: Optional[str] = None,
    ) -> dict:
        """Metni sentezleyip oynatır; sonuç bilgisi döner.
        engine: 'pyttsx3' | 'piper' | 'xtts' | None (config default)
        """
        if not text or not text.strip():
            raise ValueError("text is empty")
        overrides = dict(tone or {})
        if engine:
            overrides["engine"] = engine
        if speaker_wav:
            overrides["speaker_wav"] = speaker_wav
        if language:
            overrides["language"] = language
        self._emit_speech_liveliness_start(text, tone)
        wav = self.tts.synthesize(text, overrides=overrides or None)
        dur = self.player.play_blocking(wav)
        self._emit_speech_liveliness_end(dur)
        used_engine = overrides.get("engine") or self.cfg.get("tts", {}).get("engine")
        return {"ok": True, "engine": used_engine, "duration_sec": dur, "samplerate": wav.samplerate}

    def play_wav(self, data: bytes) -> dict:
        dur = self.player.play_wav_bytes(data)
        return {"ok": True, "duration_sec": dur}


def create_app(config_path: str | None = None) -> FastAPI:
    service = SpeakService(config_path)
    app = FastAPI()
    from modules.speak.api import get_router  # local import to avoid circular
    app.include_router(get_router(service))
    return app


def main():
    parser = argparse.ArgumentParser(description="Speech output (TTS) service")
    parser.add_argument("--config", type=str, default=None, help="Path to config.yml")
    parser.add_argument("--api", action="store_true", help="Run FastAPI server using config server.host/port")
    parser.add_argument("text", nargs="*", help="Text to speak (omit to start API)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.api or not args.text:
        import uvicorn  # type: ignore
        cfg = load_config(args.config)
        host = str(cfg.get("server", {}).get("host", "0.0.0.0"))
        port = int(cfg.get("server", {}).get("port", 8083))
        uvicorn.run(create_app(args.config), host=host, port=port)
        return

    service = SpeakService(args.config)
    txt = " ".join(args.text)
    res = service.speak(txt)
    print(res)


if __name__ == "__main__":
    main()
