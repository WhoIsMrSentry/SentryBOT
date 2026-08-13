from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.gateway.api.router import get_router


def test_healthz_exposes_degraded_bootstrap_state():
    started = {
        "_startup_health": {
            "ok": False,
            "stage": "bootstrap",
            "error": "speech module unavailable",
        }
    }
    app = FastAPI()
    app.include_router(get_router({"server": {"port": 9}}, started))

    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["startup"]["stage"] == "bootstrap"
    assert "_startup_health" not in payload["modules"]