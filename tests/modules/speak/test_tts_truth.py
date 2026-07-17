from __future__ import annotations

from modules.speak.services.tts import DummyBackend, TextToSpeech, TTSUnavailableError, UnavailableBackend


def test_missing_piper_model_is_unavailable_not_dummy_by_default() -> None:
    tts = TextToSpeech({"engine": "piper", "piper": {"model_path": "data/piper_models/__missing__/model.onnx"}})
    assert isinstance(tts.backend, UnavailableBackend)
    assert not tts.health()["available"]
    try:
        tts.synthesize("Merhaba")
    except TTSUnavailableError as exc:
        assert "piper model unavailable" in str(exc)
    else:
        raise AssertionError("missing Piper model must not synthesize dummy audio")


def test_dummy_backend_requires_explicit_allow_dummy_fallback_on_pc_dev(monkeypatch) -> None:
    monkeypatch.setenv("SENTRYBOT_RUNTIME_TARGET", "pc")
    monkeypatch.delenv("SENTRYBOT_ALLOW_TEST_TTS", raising=False)
    tts = TextToSpeech({
        "engine": "piper",
        "allow_dummy_fallback": True,
        "piper": {"model_path": "data/piper_models/__missing__/model.onnx"},
    })
    assert isinstance(tts.backend, DummyBackend)
    assert tts.health()["dummy_enabled"] is True


def test_pi_robot_target_blocks_dummy_fallback_even_when_requested(monkeypatch) -> None:
    monkeypatch.setenv("SENTRYBOT_RUNTIME_TARGET", "pi")
    monkeypatch.delenv("SENTRYBOT_ALLOW_TEST_TTS", raising=False)
    monkeypatch.delenv("SENTRYBOT_ALLOW_TEST_TONE_TTS", raising=False)
    tts = TextToSpeech({
        "engine": "piper",
        "allow_dummy_fallback": True,
        "piper": {"model_path": "data/piper_models/__missing__/model.onnx"},
    })
    assert isinstance(tts.backend, UnavailableBackend)
    health = tts.health()
    assert health["available"] is False
    assert health["dummy_enabled"] is False
    assert "dummy/test-tone TTS is disabled" in health["error"]


def test_pi_robot_target_blocks_explicit_dummy_engine(monkeypatch) -> None:
    monkeypatch.setenv("SENTRYBOT_RUNTIME_TARGET", "robot")
    monkeypatch.delenv("SENTRYBOT_ALLOW_TEST_TTS", raising=False)
    tts = TextToSpeech({"engine": "dummy", "allow_dummy_fallback": True})
    assert isinstance(tts.backend, UnavailableBackend)
    assert tts.health()["dummy_enabled"] is False


def test_pi_robot_target_allows_test_tone_only_with_explicit_env(monkeypatch) -> None:
    monkeypatch.setenv("SENTRYBOT_RUNTIME_TARGET", "pi")
    monkeypatch.setenv("SENTRYBOT_ALLOW_TEST_TTS", "1")
    tts = TextToSpeech({"engine": "dummy", "allow_dummy_fallback": True})
    assert isinstance(tts.backend, DummyBackend)
    assert tts.health()["dummy_enabled"] is True


def test_speak_status_reports_unavailable_tts() -> None:
    tts = TextToSpeech({"engine": "piper", "piper": {"model_path": "data/piper_models/__missing__/model.onnx"}})
    health = tts.health()
    assert health["available"] is False
    assert health["backend"] == "UnavailableBackend"
    assert "piper model unavailable" in health["error"]
