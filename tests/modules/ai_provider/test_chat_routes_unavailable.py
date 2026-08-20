from fastapi import FastAPI
from starlette.testclient import TestClient

from modules.ai_provider.api.chat_routes import get_chat_router


class MissingModelChat:
    def chat(self, query):
        raise RuntimeError('{"detail":"Not Found"} (status code: 404)')


class TranslatorStub:
    BRIDGE_LANG = "en"

    class Cfg:
        enabled = False
        default_source_lang = "tr"

    cfg = Cfg()

    def normalize_lang(self, value, fallback="tr"):
        return value or fallback

    def detect_language(self, query):
        return "tr"

    def to_bridge(self, query, source):
        return query

    def from_bridge(self, answer, target):
        return answer


def test_chat_returns_ok_false_for_missing_ollama_model_without_500():
    app = FastAPI()
    app.include_router(get_chat_router(
        MissingModelChat(),
        TranslatorStub(),
        "missing-model:latest",
        "ollama",
        "sentry",
        "",
        1.0,
        False,
    ), prefix="/ollama")
    client = TestClient(app)

    resp = client.post("/ollama/chat", params={"query": "Merhaba"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["error"] == "llm_model_unavailable"
    assert data["answer"] == ""
