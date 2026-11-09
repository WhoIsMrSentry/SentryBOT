from __future__ import annotations

from fastapi.testclient import TestClient

from modules.gateway.config_loader import load_config
from modules.gateway.services.bootstrap import bootstrap
from modules.gateway.xGatewayService import create_app


def test_bootstrap_import():
    assert callable(bootstrap)


def test_config_loader():
    cfg = load_config()
    assert isinstance(cfg, dict)
    assert "include" in cfg


def test_gateway_create_app_healthz(monkeypatch):
    monkeypatch.setenv("SENTRYBOT_DISABLE_AUTOSTART", "true")
    monkeypatch.setattr(
        "modules.gateway.xGatewayService.load_config",
        lambda _p=None: {"include": {"state_manager": True}},
    )
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert "ok" in resp.json()
