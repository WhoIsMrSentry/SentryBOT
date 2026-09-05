from __future__ import annotations

import asyncio
from pathlib import Path

import yaml


def test_recognizer_status_reports_speech_recognition(tmp_path: Path) -> None:
    from modules.voice.speech.services.recognizer import Recognizer

    rec = Recognizer({"language": "tr"})
    status = rec.status()

    assert status["engine"] == "speech_recognition"
    assert status["language"] == "tr"
    assert "sr_available" in status


def test_speech_service_status_with_speech_recognition(tmp_path: Path) -> None:
    from modules.voice.speech.xSpeechService import SpeechService

    cfg = {
        "audio": {"device": None, "samplerate": 16000, "channels": 1, "dtype": "int16", "frame_ms": 30},
        "recognition": {
            "language": "tr",
            "default_language": "tr",
            "source_language": "tr",
            "auto_language": True,
            "samplerate": 16000,
            "vad": {"enabled": False},
        },
        "direction": {"enabled": False},
    }
    config_path = tmp_path / "speech.yml"
    config_path.write_text(yaml.safe_dump({"speech": cfg}), encoding="utf-8")

    service = SpeechService(str(config_path))
    status = service.stt_status()

    assert status["primary_language"] == "tr"
    assert "available" in status


def test_speech_router_start_returns_status(tmp_path: Path) -> None:
    from modules.voice.speech.xSpeechService import SpeechService
    from modules.voice.speech.api.router import get_router

    cfg = {
        "audio": {"device": None, "samplerate": 16000, "channels": 1, "dtype": "int16", "frame_ms": 30},
        "recognition": {
            "language": "tr",
            "default_language": "tr",
            "source_language": "tr",
            "auto_language": False,
            "samplerate": 16000,
            "vad": {"enabled": False},
        },
        "direction": {"enabled": False},
    }
    config_path = tmp_path / "speech.yml"
    config_path.write_text(yaml.safe_dump({"speech": cfg}), encoding="utf-8")
    service = SpeechService(str(config_path))
    router = get_router(service)
    start_route = next(route for route in router.routes if getattr(route, "path", "") == "/speech/start")

    result = asyncio.run(start_route.endpoint())
    assert "ok" in result
