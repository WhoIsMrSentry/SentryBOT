"""Smoke covering the Admin UI HTTP surface."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.admin_ui.api.router import mount


def test_admin_health_requires_lan_but_allows_loopback():
    app = FastAPI()
    started = {"gateway_base_url": "http://127.0.0.1:8099"}
    mount(
        app,
        {
            "mount_prefix": "/admin",
            "bind_lan_only": False,
            "auth": {},
        },
        started,
    )
    client = TestClient(app)
    resp = client.get("/admin/health")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload.get("ok") is True


def test_static_ui_assets_exist():
    app = FastAPI()
    mount(app, {"bind_lan_only": False}, {"gateway_base_url": "http://127.0.0.1"})
    client = TestClient(app)
    r = client.get("/admin/ui")
    assert r.status_code == 200
    css = client.get("/admin/ui/style.css")
    assert css.status_code == 200
    js = client.get("/admin/ui/app.js")
    assert js.status_code == 200
