from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.system_control.telemetry.xTelemetryService import create_app


def test_create_app():
    app = create_app()
    assert app is not None


def test_metrics_writes_host_gauges():
    from modules.system_control.telemetry.api.router import get_router

    snap = MagicMock()
    snap.cpu_temp_c = 42.5
    snap.cpu_load_1m = 0.31
    app = FastAPI()
    app.include_router(get_router({}))
    with patch("modules.system_control.telemetry.api.router.read_system_snapshot", return_value=snap):
        resp = TestClient(app).get("/telemetry/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert "sentrybot_cpu_temp_c 42.5" in body
    assert "sentrybot_cpu_load_1m 0.31" in body
