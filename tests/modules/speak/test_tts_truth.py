from __future__ import annotations

from modules.speak.services.tts import DummyBackend, TextToSpeech, TTSUnavailableError, UnavailableBackend


def test_missing_piper_model_is_unavailable_not_dummy_by_default() -> None:
    tts = TextToSpeech({"engine": "piper", "piper": {"model_path": "data/piper_models/__missing__/model.onnx"}})
    assert isinstance(tts.backend, UnavailableBackend)
    assert not tts.health()["available"]
    try:
        tts.synthesize("Merhaba")
    except TTSUnavailableError as exc:
        assert "piper model not found" in str(exc)
    else:
        raise AssertionError("missing Piper model must not synthesize dummy audio")


def test_dummy_backend_requires_explicit_allow_dummy_fallback(monkeypatch) -> None:
    monkeypatch.delenv("SENTRYBOT_ALLOW_TEST_TTS", raising=False)
    tts = TextToSpeech({
        "engine": "piper",
        "allow_dummy_fallback": True,
        "piper": {"model_path": "data/piper_models/__missing__/model.onnx"},
    })
    assert isinstance(tts.backend, UnavailableBackend)
    assert tts.health()["available"] is False


def test_dummy_fallback_enabled_when_explicitly_requested(monkeypatch) -> None:
    monkeypatch.setenv("SENTRYBOT_ALLOW_TEST_TTS", "1")
    tts = TextToSpeech({
        "engine": "piper",
        "allow_dummy_fallback": True,
        "piper": {"model_path": "data/piper_models/__missing__/model.onnx"},
    })
    assert isinstance(tts.backend, DummyBackend)
    health = tts.health()
    assert health["available"] is True


def test_blocks_explicit_dummy_engine_without_env_var(monkeypatch) -> None:
    monkeypatch.delenv("SENTRYBOT_ALLOW_TEST_TTS", raising=False)
    tts = TextToSpeech({"engine": "dummy", "allow_dummy_fallback": True})
    assert isinstance(tts.backend, UnavailableBackend)
    assert tts.health()["available"] is False


def test_allows_test_tone_only_with_explicit_env(monkeypatch) -> None:
    monkeypatch.setenv("SENTRYBOT_ALLOW_TEST_TTS", "1")
    tts = TextToSpeech({"engine": "dummy", "allow_dummy_fallback": True})
    assert isinstance(tts.backend, DummyBackend)
    assert tts.health()["available"] is True


def test_speak_status_reports_unavailable_tts() -> None:
    tts = TextToSpeech({"engine": "piper", "piper": {"model_path": "data/piper_models/__missing__/model.onnx"}})
    health = tts.health()
    assert health["available"] is False
    assert health["backend"] == "UnavailableBackend"
    assert "piper model not found" in health["error"]
