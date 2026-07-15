from __future__ import annotations

from modules.ollama.api.router import _should_use_persona_model


def test_should_use_persona_model_for_ollama_when_not_single_model() -> None:
    assert _should_use_persona_model("ollama", False, True) is True


def test_should_not_use_persona_model_when_single_model_mode() -> None:
    assert _should_use_persona_model("ollama", True, True) is False


def test_should_not_use_persona_model_for_google_provider() -> None:
    assert _should_use_persona_model("google_ai_studio", False, True) is False


def test_should_not_use_persona_model_when_disabled() -> None:
    assert _should_use_persona_model("ollama", False, False) is False
