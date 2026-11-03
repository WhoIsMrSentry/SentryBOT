from __future__ import annotations

from modules.voice.speaker_id.xSpeakerIdService import create_app, SpeakerIdService


def test_create_app():
    app = create_app()
    assert app is not None


def test_service_initialization():
    svc = SpeakerIdService()
    assert svc is not None
    assert isinstance(svc.enabled, bool)

