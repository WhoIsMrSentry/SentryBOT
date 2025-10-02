from __future__ import annotations
import argparse
import logging
from typing import Optional

try:
    from .config_loader import load_config
    from .services.tts import TextToSpeech
    from .services.player import AudioPlayer
    from .api import get_router
    from fastapi import FastAPI
except Exception:
    from config_loader import load_config  # type: ignore
    from services.tts import TextToSpeech  # type: ignore
    from services.player import AudioPlayer  # type: ignore
    from api import get_router  # type: ignore
    from fastapi import FastAPI  # type: ignore

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

    def speak(self, text: str, engine: Optional[str] = None) -> dict:
        """Metni sentezleyip oynatır; sonuç bilgisi döner.
        engine: 'pyttsx3' | 'piper' | None (config default)
        """
        if not text or not text.strip():
            raise ValueError("text is empty")
        if engine and engine != getattr(self.tts, 'backend', object()).__class__.__name__.replace('Backend','').lower():
            # Geçici: istenen engine için yeni TTS örneği oluştur (basit yaklaşım)
            cfg = dict(self.cfg.get("tts", {}))
            cfg["engine"] = engine
            self.tts = TextToSpeech(cfg)
        wav = self.tts.synthesize(text)
        dur = self.player.play_blocking(wav)
        return {"ok": True, "engine": self.cfg.get("tts", {}).get("engine"), "duration_sec": dur, "samplerate": wav.samplerate}

    def play_wav(self, data: bytes) -> dict:
        dur = self.player.play_wav_bytes(data)
        return {"ok": True, "duration_sec": dur}


def create_app(config_path: str | None = None) -> FastAPI:
    service = SpeakService(config_path)
    app = FastAPI()
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
