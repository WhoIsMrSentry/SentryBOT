from fastapi import FastAPI
from starlette.testclient import TestClient

from modules.ollama.api.health import get_health_router


class ResponseStub:
    status_code = 200
    content = b"{}"

    def __init__(self, models):
        self._models = models

    def json(self):
        return {"models": [{"name": name} for name in self._models]}


def test_ollama_health_reports_missing_model(monkeypatch):
    def fake_get(url, timeout):
        return ResponseStub(["llama3.2:3b"])

    monkeypatch.setattr("modules.ollama.api.health.requests.get", fake_get)
    app = FastAPI()
    app.include_router(get_health_router({"ollama": {"base_url": "http://127.0.0.1:11434"}}, "ollama", "qwen3.5:9b"), prefix="/ollama")

    data = TestClient(app).get("/ollama/healthz").json()

    assert data["daemon_ok"] is True
    assert data["model_available"] is False
    assert data["ok"] is False
    assert data["error"] == "ollama_model_missing"


def test_ollama_health_accepts_available_model(monkeypatch):
    def fake_get(url, timeout):
        return ResponseStub(["qwen3.5:9b"])

    monkeypatch.setattr("modules.ollama.api.health.requests.get", fake_get)
    app = FastAPI()
    app.include_router(get_health_router({"ollama": {"base_url": "http://127.0.0.1:11434"}}, "ollama", "qwen3.5:9b"), prefix="/ollama")

    data = TestClient(app).get("/ollama/healthz").json()

    assert data["daemon_ok"] is True
    assert data["model_available"] is True
    assert data["ok"] is True
