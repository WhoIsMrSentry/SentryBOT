from __future__ import annotations

from fastapi.testclient import TestClient

from modules.system_control.config_center.xConfigCenterService import create_app


def test_create_app():
    app = create_app()
    assert app is not None
    client = TestClient(app)
    resp = client.get("/config/list")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
