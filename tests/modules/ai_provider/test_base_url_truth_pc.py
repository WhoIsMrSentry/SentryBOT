from fastapi import FastAPI
from starlette.testclient import TestClient

from modules.ai_provider.api.health import get_health_router
from modules.ai_provider.config_loader import _normalize_base_url
from modules.ai_provider.services.clients import OllamaClient


def test_config_loader_rejects_gateway_self_url_for_ollama_daemon():
    assert _normalize_base_url("http://127.0.0.1:8080") == "http://127.0.0.1:11434"
    assert _normalize_base_url("http://localhost:8080/ollama/chat") == "http://127.0.0.1:11434"
    assert _normalize_base_url("@gateway/ollama/chat") == "http://127.0.0.1:11434"


def test_config_loader_keeps_real_ollama_url():
    assert _normalize_base_url("http://127.0.0.1:11434") == "http://127.0.0.1:11434"
    assert _normalize_base_url("http://192.168.1.50:11434") == "http://192.168.1.50:11434"


def test_ollama_client_rejects_gateway_self_url():
    client = OllamaClient("http://127.0.0.1:8080", "qwen3.5:9b")
    assert client.base_url == "http://127.0.0.1:11434"


class ResponseStub:
    status_code = 200
    content = b"{}"

    def json(self):
        return {"models": [{"name": "qwen3.5:9b"}]}


def test_health_corrects_gateway_self_url_before_probe(monkeypatch):
    seen = {}

    def fake_get(url, timeout):
        seen["url"] = url
        return ResponseStub()

    monkeypatch.setattr("modules.ai_provider.api.health.requests.get", fake_get)
    app = FastAPI()
    app.include_router(get_health_router({"ollama": {"base_url": "http://127.0.0.1:8080"}}, "ollama", "qwen3.5:9b"), prefix="/ollama")

    data = TestClient(app).get("/ollama/healthz").json()

    assert seen["url"] == "http://127.0.0.1:11434/api/tags"
    assert data["base_url"] == "http://127.0.0.1:11434"
    assert data["configured_base_url"] == "http://127.0.0.1:8080"
    assert data["base_url_corrected"] is True
    assert data["ok"] is True
