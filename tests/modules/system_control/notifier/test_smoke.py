from __future__ import annotations

from fastapi.testclient import TestClient

from modules.system_control.notifier.xNotifierService import create_app


def test_create_app():
    app = create_app()
    assert app is not None
    client = TestClient(app)
    resp = client.get("/notify/healthz")
    assert resp.status_code == 200
    assert resp.json().get("ok") is True
