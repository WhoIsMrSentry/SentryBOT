from __future__ import annotations

from modules.ollama.services.chat import OllamaChatService


class _FakeClient:
    def __init__(self) -> None:
        self.models = []

    def chat(self, messages, format=None, *, options=None, model=None):
        self.models.append(model)
        return {"message": {"content": "ok"}}


def test_chat_uses_persona_model_by_default():
    fake = _FakeClient()
    svc = OllamaChatService(fake, persona_name="sentry")

    result = svc.chat("hello")

    assert result["text"] == "ok"
    assert fake.models[-1] == "sentry"


def test_chat_can_skip_persona_model_override():
    fake = _FakeClient()
    svc = OllamaChatService(fake, persona_name="sentry", use_persona_as_model=False)

    result = svc.chat("hello")

    assert result["text"] == "ok"
    assert fake.models[-1] is None
