"""Comprehensive async/sync self-heal, exception path, system probe, and API tests for diagnostics."""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time

import httpx
from fastapi import FastAPI
from starlette.testclient import TestClient

from modules.system_control.diagnostics.api.router import get_router
from modules.system_control.diagnostics.config_loader import load_config
from modules.system_control.diagnostics.services.selftest import (
    _HEAL_STATE,
    clear_heal_state,
    run_http_checks,
    run_http_checks_async,
    run_local_system_checks,
)


class _FakeSyncResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = {} if payload is None else payload
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


def test_diagnostics_exception_path_triggers_heal_with_cooldown(monkeypatch, caplog):
    clear_heal_state()
    heal_calls = []
    notify_calls = []

    class _TimeoutClient:
        def __init__(self, base_url):
            pass

        def request(self, method, path, timeout=None, json=None):
            if path.endswith("/notify/telegram"):
                notify_calls.append(json)
                raise RuntimeError("telegram offline")
            if method == "POST":
                heal_calls.append(path)
                return _FakeSyncResp(200)
            raise TimeoutError("probe timed out")

        def close(self):
            pass

    class _FakeHttpx:
        Client = _TimeoutClient

    monkeypatch.setitem(sys.modules, "httpx", _FakeHttpx)
    try:
        checks = {
            "camera": {
                "method": "GET",
                "path": "/camera/healthz",
                "critical": True,
                "heal": {"method": "POST", "path": "/camera/start"},
            }
        }
        first = run_http_checks(
            "http://127.0.0.1:8080",
            checks,
            self_heal={"enabled": True, "hard_heal_cooldown_s": 60.0},
            notify={"enabled": True, "endpoint": "/notify/telegram"},
        )
        assert first["ok"] is False
        assert first["camera"]["heal"]["ok"] is True
        assert heal_calls == ["http://127.0.0.1:8080/camera/start"]
        assert len(notify_calls) == 1
        assert "Diagnostics notify POST" in caplog.text

        second = run_http_checks(
            "http://127.0.0.1:8080",
            checks,
            self_heal={"enabled": True, "hard_heal_cooldown_s": 60.0},
        )
        assert heal_calls == ["http://127.0.0.1:8080/camera/start"]
        assert second["camera"]["heal_suppressed"]["reason"] == "hard_heal_cooldown"
    finally:
        clear_heal_state()


def test_speak_and_speech_status_body_validation(monkeypatch):
    clear_heal_state()

    class _BodyClient:
        def __init__(self, base_url):
            pass

        def request(self, method, path, timeout=None, json=None):
            if path == "/speak/status":
                return _FakeSyncResp(200, {"ready": False})
            if path == "/speech/status":
                return _FakeSyncResp(200, {"model_ready": True})
            return _FakeSyncResp(200, {"ok": True})

        def close(self):
            pass

    monkeypatch.setitem(sys.modules, "httpx", type("_M", (), {"Client": _BodyClient}))
    try:
        out = run_http_checks(
            "http://127.0.0.1:8080",
            {
                "speak": {"method": "GET", "path": "/speak/status", "critical": True},
                "speech": {"method": "GET", "path": "/speech/status", "critical": True},
            },
        )
        assert out["ok"] is False
        assert out["failed"] == ["speak"]
        assert out["speech"]["ok"] is True
    finally:
        clear_heal_state()


def test_async_checks_run_concurrently_and_system_checks(monkeypatch):
    clear_heal_state()

    class _SlowAsyncClient:
        def __init__(self, base_url):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, method, path, timeout=None, json=None):
            await asyncio.sleep(0.06)
            return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(httpx, "AsyncClient", _SlowAsyncClient)
    try:
        t0 = time.monotonic()
        checks = {f"svc_{i}": {"method": "GET", "path": f"/svc_{i}/healthz", "critical": True} for i in range(6)}
        out = asyncio.run(
            run_http_checks_async(
                "http://127.0.0.1:8080",
                checks,
                system_checks={"enabled": True, "disk_path": ".", "min_free_gb": 0.01, "min_free_mb": 1.0},
            )
        )
        elapsed = time.monotonic() - t0
        assert elapsed < 0.25
        assert out["ok"] is True
        assert "system" in out
        assert "disk" in out["system"] and "pressure" in out["system"]
    finally:
        clear_heal_state()


def test_diagnostics_router_and_thread_safe_state(monkeypatch):
    clear_heal_state()
    sys_info = run_local_system_checks({"disk_path": ".", "min_free_gb": 0.01, "min_free_mb": 1.0})
    assert "disk" in sys_info

    cfg = load_config()
    assert cfg["notify"]["endpoint"] == "/notify/telegram"
    assert {"wakeword", "oled_faces", "agent_core", "autonomy"}.issubset(set(cfg["checks"].keys()))

    class _RouterAsyncClient:
        def __init__(self, base_url):
            self.base_url = base_url

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, method, path, timeout=None, json=None):
            if path == "/speak/status":
                return httpx.Response(200, json={"ready": True})
            if path == "/speech/status":
                return httpx.Response(200, json={"model_ready": True})
            return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(httpx, "AsyncClient", _RouterAsyncClient)
    try:
        app = FastAPI()
        app.include_router(get_router(cfg))
        client = TestClient(app)

        res = client.post("/diagnostics/run")
        assert res.status_code == 200
        payload = res.json()
        assert payload["ok"] is True
        assert "system" in payload
        assert client.get("/diagnostics/report").json()["ok"] is True

        # Concurrent _HEAL_STATE access check
        errs = []

        def _mutator():
            try:
                for _ in range(10):
                    with threading.Lock():
                        _ = _HEAL_STATE.get("camera")
                    clear_heal_state()
            except Exception as exc:
                errs.append(exc)

        ts = [threading.Thread(target=_mutator) for _ in range(3)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert errs == []
    finally:
        clear_heal_state()
