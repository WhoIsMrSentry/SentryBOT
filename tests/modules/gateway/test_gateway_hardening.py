from __future__ import annotations

import asyncio
from types import SimpleNamespace
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx

import modules.gateway.xGatewayService as gw_service
from modules.gateway.api.router import get_router
from modules.gateway.config_loader import DEFAULT_CONFIG, load_config
from modules.gateway.services import agent_api_compat, agent_core_binding, bootstrap_config
from modules.gateway.services.bootstrap import bootstrap
from modules.gateway.services.bootstrap_hardware import _wire_arduino_neopixel


def test_security_rejects_x_role_admin_header_escalation(monkeypatch) -> None:
    monkeypatch.delenv("SENTRY_API_KEY", raising=False)
    cfg = {
        "server": {"host": "127.0.0.1", "port": 0},
        "include": {},
        "security": {
            "enabled": True,
            "trust_loopback": False,
            "api_keys": ["user-key"],
            "admin_keys": ["admin-key"],
            "admin_write_prefixes": ["/config"],
        },
    }
    monkeypatch.setattr(gw_service, "load_config", lambda config_path=None: cfg)
    app = gw_service.create_app()

    @app.post("/config/reload")
    def _reload():
        return {"ok": True}

    client = TestClient(app, client=("203.0.113.10", 50000))
    # Forged X-Role: admin with non-admin key MUST still receive 403
    forged = client.post(
        "/config/reload",
        headers={"X-API-Key": "user-key", "X-Role": "admin"},
    )
    assert forged.status_code == 403

    real_admin = client.post("/config/reload", headers={"X-API-Key": "admin-key"})
    assert real_admin.status_code == 200


def test_config_loader_handles_explicit_file_and_deepcopies_default(tmp_path) -> None:
    cfg_file = tmp_path / "custom_gateway.yml"
    cfg_file.write_text("server:\n  port: 9999\ninclude:\n  arduino: false\n", encoding="utf-8")

    orig_include = dict(DEFAULT_CONFIG["include"])
    loaded = load_config(str(cfg_file))

    assert loaded["server"]["port"] == 9999
    assert loaded["include"]["arduino"] is False
    assert DEFAULT_CONFIG["include"] == orig_include


def test_bootstrap_config_cache_invalidates_on_mtime_change(monkeypatch, tmp_path) -> None:
    agent_file = tmp_path / "agent.yaml"
    agent_file.write_text("agent:\n  name: v1\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_CFG", str(agent_file))
    bootstrap_config.invalidate_agent_cfg_cache()

    first = bootstrap_config._root_agent_cfg()
    assert first.get("agent", {}).get("name") == "v1"

    agent_file.write_text("agent:\n  name: v2\n", encoding="utf-8")
    # Ensure mtime_ns advances deterministically on fast filesystems
    stat = agent_file.stat()
    import os

    os.utime(agent_file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    second = bootstrap_config._root_agent_cfg()
    assert second.get("agent", {}).get("name") == "v2"
    bootstrap_config.invalidate_agent_cfg_cache()


def test_in_memory_health_and_readyz_without_loopback_http(monkeypatch) -> None:
    def _forbid_http(*_args, **_kwargs):
        raise AssertionError("sync httpx.Client should not be called by gateway health routes")

    monkeypatch.setattr(httpx, "Client", _forbid_http)

    class HealthySvc:
        def health(self):
            return {"ok": True, "detail": "in_memory"}

    class FailingSvc:
        def health(self):
            return {"ok": False, "detail": "sensor_down"}

    started = {
        "_startup_health": {"ok": True, "stage": "ready"},
        "_boot_total_ms": 12.5,
        "_boot_manifest": [
            {"module": "ok_svc", "status": "active", "duration_ms": 2.0, "reason": "ok"},
            {"module": "bad_svc", "status": "active", "duration_ms": 10.5, "reason": "ok"},
        ],
        "ok_svc": HealthySvc(),
        "bad_svc": FailingSvc(),
        "stub_svc": {"kind": "stub", "available": False, "reason": "hardware_disabled"},
    }

    app = FastAPI()
    app.include_router(get_router({"include": {}}, started))
    client = TestClient(app)

    hz = client.get("/healthz")
    assert hz.status_code == 200
    assert hz.json()["ok"] is False
    assert hz.json()["modules"]["ok_svc"]["ok"] is True
    assert hz.json()["modules"]["bad_svc"]["ok"] is False
    assert hz.json()["modules"]["stub_svc"]["kind"] == "stub"

    hl = client.get("/health")
    assert hl.status_code == 200
    assert hl.json()["ok"] is False
    assert hl.json()["ok_svc"]["body"]["detail"] == "in_memory"

    rz = client.get("/readyz")
    assert rz.status_code == 200
    assert rz.json()["ready"] is True
    assert rz.json()["slowest_module"]["module"] == "bad_svc"

    started["_startup_health"] = {"ok": False, "stage": "bootstrap"}
    rz_fail = client.get("/readyz")
    assert rz_fail.status_code == 503
    assert rz_fail.json()["ready"] is False


def test_bootstrap_calibration_gate_and_camera_disabled_stub(monkeypatch, tmp_path) -> None:
    import modules.camera.config_loader as cam_cfg

    agent_file = tmp_path / "agent_cam_off.yaml"
    agent_file.write_text("camera:\n  enabled: false\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_CFG", str(agent_file))
    bootstrap_config.invalidate_agent_cfg_cache()
    monkeypatch.delenv("SENTRYBOT_NO_HARDWARE", raising=False)
    monkeypatch.delenv("SENTRYBOT_SKIP_CAMERA_AUTOSTART", raising=False)
    monkeypatch.setattr(cam_cfg, "load_config", lambda _p=None: {"enabled": False})

    app = FastAPI()
    try:
        started = bootstrap(
            app,
            {
                "include": {
                    "social_db": False,
                    "agent_core": False,
                    "speaker_id": False,
                    "camera": True,
                    "calibration": False,
                }
            },
        )
    finally:
        monkeypatch.delenv("AGENT_CFG", raising=False)
        bootstrap_config.invalidate_agent_cfg_cache()

    assert "calibration" not in started
    assert isinstance(started.get("camera"), dict)
    assert started["camera"]["kind"] == "stub"
    assert started["camera"]["reason"] == "disabled_in_config"
    assert any(m["module"] == "camera" and m["status"] == "stub" for m in started["_boot_manifest"])
    assert any(m["module"] == "calibration" and m["status"] == "disabled" for m in started["_boot_manifest"])


def test_arduino_neopixel_bridge_flushes_trailing_event_and_cleans_up() -> None:
    handlers = []
    fills = []

    fake_arduino = SimpleNamespace(register_event_handler=lambda fn: handlers.append(fn))
    fake_neo = SimpleNamespace(fill=lambda r, g, b, segment=None: fills.append((r, g, b)))
    started = {
        "arduino": fake_arduino,
        "neopixel": fake_neo,
    }

    _wire_arduino_neopixel(
        FastAPI(),
        started,
        {"neopixel": {"min_interval_ms": 30}, "arduino_neopixel_bridge": {}},
    )
    assert len(handlers) == 1

    # Trigger two rapid events: first runs immediately, second is queued and flushed by timer
    handlers[0]({"event": "neopixel_request", "color": "255,0,0"})
    handlers[0]({"event": "neopixel_request", "color": "0,255,0"})
    assert fills == [(255, 0, 0)]

    deadline = time.monotonic() + 1.0
    while len(fills) < 2 and time.monotonic() < deadline:
        time.sleep(0.02)

    for hook in started.get("_cleanup_hooks", []):
        hook()

    assert fills == [(255, 0, 0), (0, 255, 0)]


def test_agent_api_compat_keywords_and_async_ollama(monkeypatch) -> None:
    assert agent_api_compat._prompt_wants_tool_action("I feel blue today") is False
    assert agent_api_compat._prompt_wants_tool_action("Tell me what you say about the red sky") is False
    assert agent_api_compat._prompt_wants_tool_action("Set the lights to blue") is True

    class FakeResp:
        content = b"{}"

        def json(self):
            return {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "set_lights", "arguments": '{"effect":"solid","color":"blue"}'}}
                    ],
                }
            }

    class FakeAsyncClient:
        async def post(self, path, json=None, **kwargs):
            return FakeResp()

    monkeypatch.setattr(agent_api_compat, "get_http_client", lambda *_a, **_k: FakeAsyncClient())

    async def _run():
        return await agent_api_compat._ollama_tool_fallback("Set the lights to blue")

    res = asyncio.run(_run())
    assert res["ok"] is True
    assert res["tool_calls"][0]["name"] == "set_lights"
    assert res["tool_calls"][0]["arguments"]["color"] == "blue"


def test_agent_core_binding_supports_from_config_and_kw_signature() -> None:
    class FromConfigAgent:
        @classmethod
        def from_config(cls, cfg, started=None):
            return cls(cfg, started)

        def __init__(self, cfg, started=None):
            self.cfg = cfg
            self.started = started

        def step(self, prompt: str):
            return {"ok": True, "prompt": prompt}

    class KwOnlyAgent:
        def __init__(self, *, config, started):
            self.config = config
            self.started = started

        def turn(self, prompt: str):
            return {"ok": True}

    obj1, errs1 = agent_core_binding._construct(FromConfigAgent, FastAPI(), {"k": 1}, {"s": 2})
    assert isinstance(obj1, FromConfigAgent) and not errs1

    obj2, errs2 = agent_core_binding._construct(KwOnlyAgent, FastAPI(), {"k": 2}, {"s": 3})
    assert isinstance(obj2, KwOnlyAgent) and not errs2
