from __future__ import annotations

import json
import sys
import time

from modules.system_control.diagnostics.services.selftest import (
    _HEAL_STATE,
    run_http_checks,
)


class _Resp:
    def __init__(self, status_code=200, text="{}"):
        self.status_code = status_code
        self.text = text

    def json(self):
        return json.loads(self.text)


def _install_fake_httpx(monkeypatch, client_cls):
    class _FakeHttpx:
        Client = client_cls

    monkeypatch.setitem(sys.modules, "httpx", _FakeHttpx)


def test_scheduler_run_once_skips_when_job_in_flight():
    import asyncio

    from modules.system_control.scheduler.services.runner import Scheduler

    async def _scenario():
        sched = Scheduler(jobs=[{"id": "slow", "kind": "http", "path": "/healthz", "every_s": 30}])
        sched._inflight["slow"] = True
        try:
            result = await sched.run_once("slow")
            assert result == {"ok": False, "error": "job_in_flight", "id": "slow"}
            missing = await sched.run_once("nope")
            assert missing["ok"] is False and missing["error"] == "job_not_found"
        finally:
            sched._inflight["slow"] = False

    asyncio.run(_scenario())


def test_selftest_heals_immediately_on_hard_failure(monkeypatch):
    _HEAL_STATE.clear()
    heal_calls: list[str] = []

    class _Client:
        def __init__(self, base_url):
            pass

        def request(self, method, path, timeout=None, json=None):
            if method == "POST":
                heal_calls.append(path)
                return _Resp(200)
            return _Resp(500)

        def close(self):
            pass

    _install_fake_httpx(monkeypatch, _Client)
    try:
        out = run_http_checks(
            "http://127.0.0.1:8080",
            {"camera": {"method": "GET", "path": "/camera/status", "critical": True,
                        "heal": {"method": "POST", "path": "/camera/start"}}},
            self_heal={"enabled": True},
        )
        assert out["ok"] is False
        assert heal_calls == ["http://127.0.0.1:8080/camera/start"]
    finally:
        _HEAL_STATE.clear()


def test_selftest_latency_only_failures_need_stabilization_window(monkeypatch):
    _HEAL_STATE.clear()
    heal_calls: list[str] = []

    class _SlowClient:
        def __init__(self, base_url):
            pass

        def request(self, method, path, timeout=None, json=None):
            if method == "POST":
                heal_calls.append(path)
            time.sleep(0.01)
            return _Resp()

        def close(self):
            pass

    _install_fake_httpx(monkeypatch, _SlowClient)
    try:
        checks = {
            "camera": {
                "method": "GET", "path": "/camera/status", "critical": True,
                "latency_warn_ms": 1,
                "heal": {"method": "POST", "path": "/camera/start"},
            }
        }
        for _ in range(2):
            out = run_http_checks(
                "http://127.0.0.1:8080", checks, self_heal={"enabled": True},
            )
            assert out["ok"] is False
            suppressed = out["camera"].get("heal_suppressed")
            assert suppressed and suppressed["reason"] == "latency_stabilization"
            assert heal_calls == []

        third = run_http_checks(
            "http://127.0.0.1:8080", checks, self_heal={"enabled": True},
        )
        assert heal_calls == ["http://127.0.0.1:8080/camera/start"]
        assert "heal_suppressed" not in third["camera"]

        fourth = run_http_checks(
            "http://127.0.0.1:8080", checks,
            self_heal={"enabled": True, "latency_heal_cooldown_s": 900},
        )
        assert heal_calls == ["http://127.0.0.1:8080/camera/start"], "cooldown must suppress immediate re-heal"
        assert fourth["camera"].get("heal_suppressed", {}).get("reason") == "latency_stabilization"
    finally:
        _HEAL_STATE.clear()
