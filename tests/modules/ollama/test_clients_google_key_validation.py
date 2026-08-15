from __future__ import annotations

import pytest

from modules.ollama.services.clients import create_llm_client


def _google_cfg(api_key: str):
    return {
        "llm": {"provider": "google_ai_studio"},
        "google_ai_studio": {
            "api_key": api_key,
            "model": "gemini-1.5-flash",
            "base_url": "https://generativelanguage.googleapis.com",
            "request_timeout": 30,
        },
    }


def test_placeholder_google_api_key_is_rejected(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        create_llm_client(_google_cfg("your-google-api-key"))


def test_valid_google_api_key_is_accepted(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    client, provider = create_llm_client(_google_cfg("AIza-test-key"))

    assert provider == "google_ai_studio"
    assert client.model == "gemini-1.5-flash"
