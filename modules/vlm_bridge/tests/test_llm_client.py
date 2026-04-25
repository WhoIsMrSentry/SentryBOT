from __future__ import annotations

from modules.vlm_bridge.services.llm_client import generate_text


class _DummyResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _DummyClient:
    def __init__(self, recorder: dict, response: _DummyResponse, timeout: float):
        self.recorder = recorder
        self.response = response
        self.timeout = timeout

    def __enter__(self):
        self.recorder["timeout"] = self.timeout
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json=None, params=None):
        self.recorder["url"] = url
        self.recorder["json"] = json
        self.recorder["params"] = params
        return self.response


def test_generate_text_legacy_generate_endpoint(monkeypatch):
    recorder = {}

    class _Httpx:
        @staticmethod
        def Client(timeout):
            return _DummyClient(
                recorder,
                _DummyResponse(200, {"response": "kisa ozet"}),
                timeout,
            )

    monkeypatch.setattr("modules.vlm_bridge.services.llm_client.httpx", _Httpx, raising=False)
    monkeypatch.setattr(
        "modules.vlm_bridge.services.llm_client._provider_hint",
        lambda: {"provider": "ollama", "google_key_ready": True},
        raising=False,
    )

    out = generate_text(
        "sahneyi ozetle",
        {"endpoint": "http://localhost:11435/api/generate", "model": "qwen3.5:9b"},
        timeout=3.0,
    )

    assert out == "kisa ozet"
    assert recorder["url"].endswith("/api/generate")
    assert recorder["json"]["model"] == "qwen3.5:9b"
    assert recorder["params"] is None


def test_generate_text_gateway_chat_endpoint(monkeypatch):
    recorder = {}

    class _Httpx:
        @staticmethod
        def Client(timeout):
            return _DummyClient(
                recorder,
                _DummyResponse(200, {"answer": "merhaba"}),
                timeout,
            )

    monkeypatch.setattr("modules.vlm_bridge.services.llm_client.httpx", _Httpx, raising=False)
    monkeypatch.setattr(
        "modules.vlm_bridge.services.llm_client._provider_hint",
        lambda: {"provider": "ollama", "google_key_ready": True},
        raising=False,
    )
    from modules.vlm_bridge.services import llm_client as _llm
    _llm._CHAT_COOLDOWN_UNTIL.clear()

    out = generate_text(
        "sahneyi ozetle",
        {"endpoint": "http://localhost:8080/ollama/chat"},
        timeout=2.5,
        response_lang="tr",
    )

    assert out == "merhaba"
    assert recorder["url"].endswith("/ollama/chat")
    assert recorder["json"] is None
    assert recorder["params"]["apply_actions"] == "false"
    assert recorder["params"]["response_lang"] == "tr"


def test_generate_text_skips_chat_when_google_key_missing(monkeypatch):
    called = {"post": 0}

    class _Httpx:
        @staticmethod
        def Client(timeout):
            class _C:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def post(self, url, json=None, params=None):
                    called["post"] += 1
                    return _DummyResponse(200, {"answer": "olmamalı"})

            return _C()

    monkeypatch.setattr("modules.vlm_bridge.services.llm_client.httpx", _Httpx, raising=False)
    monkeypatch.setattr(
        "modules.vlm_bridge.services.llm_client._provider_hint",
        lambda: {"provider": "google_ai_studio", "google_key_ready": False},
        raising=False,
    )

    out = generate_text("deneme", {"endpoint": "http://localhost:8080/ollama/chat"})

    assert out is None
    assert called["post"] == 0


def test_generate_text_skips_direct_ollama_endpoint_when_google_provider(monkeypatch):
    called = {"post": 0}

    class _Httpx:
        @staticmethod
        def Client(timeout):
            class _C:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def post(self, url, json=None, params=None):
                    called["post"] += 1
                    return _DummyResponse(200, {"message": {"content": "olmamalı"}})

            return _C()

    monkeypatch.setattr("modules.vlm_bridge.services.llm_client.httpx", _Httpx, raising=False)
    monkeypatch.setattr(
        "modules.vlm_bridge.services.llm_client._provider_hint",
        lambda: {"provider": "google_ai_studio", "google_key_ready": True},
        raising=False,
    )

    out = generate_text(
        "deneme",
        {"endpoint": "http://remote-ollama-host:11434/api/chat", "model": "qwen3.5:9b"},
    )

    assert out is None
    assert called["post"] == 0


def test_generate_text_chat_uses_cooldown_after_failure(monkeypatch):
    recorder = {"post_calls": 0}

    class _Httpx:
        @staticmethod
        def Client(timeout):
            class _C:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def post(self, url, json=None, params=None):
                    recorder["post_calls"] += 1
                    return _DummyResponse(500, {})

            return _C()

    monkeypatch.setattr("modules.vlm_bridge.services.llm_client.httpx", _Httpx, raising=False)
    monkeypatch.setattr(
        "modules.vlm_bridge.services.llm_client._provider_hint",
        lambda: {"provider": "ollama", "google_key_ready": True},
        raising=False,
    )
    from modules.vlm_bridge.services import llm_client as _llm
    _llm._CHAT_COOLDOWN_UNTIL.clear()

    cfg = {
        "endpoint": "http://localhost:8080/ollama/chat",
        "cooldown_on_failure_s": 60,
    }
    first = generate_text("ilk", cfg)
    second = generate_text("ikinci", cfg)

    assert first is None
    assert second is None
    assert recorder["post_calls"] == 1


def test_generate_text_direct_api_chat_uses_model_payload(monkeypatch):
    recorder = {}

    class _Httpx:
        @staticmethod
        def Client(timeout):
            return _DummyClient(
                recorder,
                _DummyResponse(200, {"message": {"content": "dogrudan chat"}}),
                timeout,
            )

    monkeypatch.setattr("modules.vlm_bridge.services.llm_client.httpx", _Httpx, raising=False)
    monkeypatch.setattr(
        "modules.vlm_bridge.services.llm_client._provider_hint",
        lambda: {"provider": "ollama", "google_key_ready": True},
        raising=False,
    )

    out = generate_text(
        "sahneyi ozetle",
        {"endpoint": "http://remote-ollama-host:11434/api/chat", "model": "qwen3.5:9b"},
        timeout=2.0,
    )

    assert out == "dogrudan chat"
    assert recorder["url"].endswith("/api/chat")
    assert recorder["json"]["model"] == "qwen3.5:9b"
    assert recorder["json"]["messages"][0]["role"] == "user"


def test_generate_text_normalizes_api_tags_to_api_chat(monkeypatch):
    recorder = {}

    class _Httpx:
        @staticmethod
        def Client(timeout):
            return _DummyClient(
                recorder,
                _DummyResponse(200, {"message": {"content": "normalized"}}),
                timeout,
            )

    monkeypatch.setattr("modules.vlm_bridge.services.llm_client.httpx", _Httpx, raising=False)
    monkeypatch.setattr(
        "modules.vlm_bridge.services.llm_client._provider_hint",
        lambda: {"provider": "ollama", "google_key_ready": True},
        raising=False,
    )

    out = generate_text(
        "deneme",
        {"endpoint": "http://remote-ollama-host:11434/api/tags", "model": "qwen3.5:9b"},
    )

    assert out == "normalized"
    assert recorder["url"].endswith("/api/chat")
