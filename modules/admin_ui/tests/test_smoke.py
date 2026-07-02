"""Smoke test for the Admin UI module.

Admin UI does not run as its own standalone service; it is mounted into a
host FastAPI application (normally the gateway) via
:func:`modules.admin_ui.api.router.mount`. This smoke test verifies that the
router mounts cleanly on a bare FastAPI app and that the health endpoint
responds with a 200.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.admin_ui.api.router import mount


def test_mount_creates_working_app_with_health_endpoint():
    app = FastAPI()
    started = {"gateway_base_url": "http://127.0.0.1:8080"}

    mount(app, {"bind_lan_only": False, "auth": {}}, started)

    assert app is not None

    client = TestClient(app)
    resp = client.get("/admin/health")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload.get("ok") is True
