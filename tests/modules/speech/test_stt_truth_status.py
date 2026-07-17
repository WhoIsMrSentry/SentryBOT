from __future__ import annotations

import asyncio
from pathlib import Path

import yaml


def test_recognizer_status_reports_missing_model(tmp_path: Path) -> None:
    from modules.speech.services.recognizer import Recognizer

    missing = tmp_path / "missing-vosk"
    rec = Recognizer({"language": "tr", "language_models": {"tr": str(missing)}})
    status = rec.status()

    assert status["ok"] is False
    assert status["model_exists"] is False
    assert status["model_path"] == str(missing)
    assert "model" in status["error"]


def test_speech_service_status_rejects_missing_primary_model(tmp_path: Path) -> None:
    from modules.speech.xSpeechService import SpeechService

    cfg = {
        "audio": {"device": None, "samplerate": 16000, "channels": 1, "dtype": "int16", "frame_ms": 30},
        "recognition": {
            "language": "tr",
            "default_language": "tr",
            "source_language": "tr",
            "auto_language": True,
            "auto_switch_model": True,
            "dual_decode_languages": ["tr", "en"],
            "language_models": {"tr": str(tmp_path / "vosk-tr"), "en": str(tmp_path / "vosk-en")},
            "samplerate": 16000,
            "vad": {"enabled": False},
        },
        "direction": {"enabled": False},
    }
    config_path = tmp_path / "speech.yml"
    config_path.write_text(yaml.safe_dump({"speech": cfg}), encoding="utf-8")

    service = SpeechService(str(config_path))
    status = service.stt_status()

    assert status["available"] is False
    assert status["model_ready"] is False
    assert status["primary_language"] == "tr"
    assert "tr" in status["missing_languages"]


def test_speech_router_start_returns_stt_unavailable(tmp_path: Path) -> None:
    from modules.speech.xSpeechService import SpeechService
    from modules.speech.api.router import get_router

    cfg = {
        "audio": {"device": None, "samplerate": 16000, "channels": 1, "dtype": "int16", "frame_ms": 30},
        "recognition": {
            "language": "tr",
            "default_language": "tr",
            "source_language": "tr",
            "auto_language": False,
            "auto_switch_model": False,
            "language_models": {"tr": str(tmp_path / "vosk-tr")},
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

    assert result["ok"] is False
    assert result["reason"] == "stt_unavailable"
    assert result["stt"]["available"] is False
