from __future__ import annotations

import logging

from modules.runtime_console import RuntimeConsoleLogHandler, classify_record, publish_event
from modules.runtime_console.dashboard import should_hide_background_message
from modules.runtime_console.renderer import ConsoleRenderer


def test_smoke_event_bus_and_renderer():
    event = publish_event("VISION", "Camera ready", status="OK", duration_ms=12)
    renderer = ConsoleRenderer(colors=False, max_width=70, border="ascii")
    out = renderer.box("TEST", [renderer.event_line(event)])
    assert "VISION" in out
    assert "Camera ready" in out


def test_classify_and_background_filter():
    record = logging.LogRecord("modules.vlm_bridge.api", logging.INFO, __file__, 1, "ok", (), None)
    assert classify_record(record) == "VISION"
    assert should_hide_background_message("GET /camera/healthz 200") is True
    assert should_hide_background_message("Wakeword detected") is False


def test_handler_instantiates():
    handler = RuntimeConsoleLogHandler(level=logging.INFO, colors=False, mode="compact", max_message_width=60)
    assert handler is not None


def test_http_router_healthz():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from modules.runtime_console.api.router import router

    app = FastAPI()
    app.include_router(router)
    resp = TestClient(app).get("/runtime_console/healthz")
    assert resp.status_code == 200
    assert resp.json().get("ok") is True
