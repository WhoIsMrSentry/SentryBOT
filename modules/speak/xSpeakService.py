from __future__ import annotations
import argparse
import logging
from typing import Optional

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

    def speak(self, text: str, engine: Optional[str] = None, tone: Optional[dict] = None) -> dict:
        """Metni sentezleyip oynatır; sonuç bilgisi döner.
        engine: 'pyttsx3' | 'piper' | None (config default)
        """
        if not text or not text.strip():
            raise ValueError("text is empty")
        overrides = dict(tone or {})
        if engine:
            overrides["engine"] = engine
        wav = self.tts.synthesize(text, overrides=overrides or None)
        dur = self.player.play_blocking(wav)
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
