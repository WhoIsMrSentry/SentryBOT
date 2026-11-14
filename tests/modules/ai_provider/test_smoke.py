from __future__ import annotations

from fastapi.testclient import TestClient

import modules.ai_provider as m
from modules.ai_provider.xOllamaService import create_app


def test_import():
    assert m is not None
    app = create_app()
    client = TestClient(app)
    persona = client.get("/ollama/persona")
    assert persona.status_code == 200
    assert persona.json().get("ok") is True
    personas = client.get("/ollama/personas")
    assert personas.status_code == 200
    assert "items" in personas.json()
