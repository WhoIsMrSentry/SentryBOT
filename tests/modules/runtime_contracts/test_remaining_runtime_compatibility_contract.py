from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.autonomy.services.brain_parts.responses import (
    AUTONOMY_LLM_TAG_COMPATIBILITY_CONTRACT,
    AUTONOMY_LLM_TAG_COMPATIBILITY_ROLE,
    ResponseTagMixin,
)
from modules.camera.api.router import (
    CAMERA_RUNNER_STATUS_COMPATIBILITY_CONTRACT,
    CAMERA_RUNNER_STATUS_COMPATIBILITY_ROLE,
    get_router,
)
import importlib
from modules.runtime_console import tui_v2


gateway_bootstrap = importlib.import_module("modules.gateway.services.bootstrap")


def test_legacy_llm_inline_tags_are_explicit_compatibility_parser():
    assert AUTONOMY_LLM_TAG_COMPATIBILITY_CONTRACT is True
    assert AUTONOMY_LLM_TAG_COMPATIBILITY_ROLE == "legacy_inline_llm_tag_adapter"

    class Parser(ResponseTagMixin):
        pass

    parser = Parser()
    cleaned, commands, blocks = parser._extract_legacy_tags(
        "Merhaba [cmd:head_nod, scan] [[lights palette=calm_violet intensity=0.5]]"
    )
    assert cleaned == "Merhaba"
    assert commands == ["head_nod", "scan"]
    assert blocks == [{"type": "lights", "attrs": {"palette": "calm_violet", "intensity": 0.5}}]


def test_camera_runner_status_compatibility_path_reports_without_starting_camera():
    assert CAMERA_RUNNER_STATUS_COMPATIBILITY_CONTRACT is True
    assert CAMERA_RUNNER_STATUS_COMPATIBILITY_ROLE == "imx500_runner_status_backcompat_adapter"

    class Capture:
        gave_up = False

        def status(self):
            return {"has_frame": True, "gave_up": False}

    class CompatRunner:
        available = True
        running = False

        class cfg:
            enabled = True

    app = FastAPI()
    app.include_router(get_router(Capture(), 30, enabled=True, imx500_runner=CompatRunner()))
    data = TestClient(app).get("/status").json()
    assert data["imx500"]["reason"] == "compatibility_runner"
    assert data["imx500"]["enabled"] is True
    assert data["imx500"]["available"] is True


def test_gateway_fastapi_event_registration_marker_is_exported():
    assert gateway_bootstrap.GATEWAY_EVENT_REGISTRATION_COMPATIBILITY_CONTRACT is True
    assert gateway_bootstrap.GATEWAY_EVENT_REGISTRATION_ROLE == "fastapi_startup_shutdown_compatibility_adapter"


def test_runtime_console_preview_warning_marker_is_exported():
    assert tui_v2.RUNTIME_CONSOLE_PREVIEW_WARNING_COMPATIBILITY_CONTRACT is True
    assert tui_v2.RUNTIME_CONSOLE_PREVIEW_WARNING_ROLE == "pc_dev_robot_preview_status_classifier"
