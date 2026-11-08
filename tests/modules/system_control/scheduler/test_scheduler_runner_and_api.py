"""Execution, retry, HTTP pooling, HH:MM scheduling, persistence, and API tests for scheduler."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import FastAPI
from starlette.testclient import TestClient

from modules.common.job_types import JobContext, JobHandler, get_job_registry
from modules.system_control.scheduler.api.router import get_router
from modules.system_control.scheduler.services.runner import Scheduler


class _CountingHandler(JobHandler):
    kind = "_test_counting"

    def __init__(self):
        self.calls = 0
        self.contexts = []
        self.fail_times = 0

    async def execute(self, context: JobContext):
        self.calls += 1
        self.contexts.append(context)
        if self.calls <= self.fail_times:
            raise RuntimeError("transient error")
        return {"count": self.calls}


def test_scheduler_execute_passes_job_context_and_retries(monkeypatch):
    registry = get_job_registry()
    registry.register(_CountingHandler)
    handler: _CountingHandler = registry.get("_test_counting")  # type: ignore[assignment]
    handler.fail_times = 1

    try:
        sleep_calls = []
        real_sleep = asyncio.sleep

        async def _fake_sleep(sec: float):
            sleep_calls.append(sec)
            await real_sleep(0)

        monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

        sched = Scheduler(services={"custom_dep": "ok"})
        sched.add_or_update_job(
            {
                "id": "ctx_job",
                "kind": "_test_counting",
                "max_retries": 1,
                "retry_delay_s": 0.25,
                "every_s": 10.0,
            }
        )
        res = asyncio.run(sched.run_once("ctx_job"))
        assert res["ok"] is True
        assert res["attempts"] == 2
        assert res["result"] == {"count": 2}
        assert sleep_calls == [0.25]
        assert isinstance(handler.contexts[0], JobContext)
        assert handler.contexts[0].services["custom_dep"] == "ok"

        assert sched.remove_job("ctx_job") is True
        assert "ctx_job" not in sched.list_results()
    finally:
        registry.unregister("_test_counting")


def test_scheduler_reuses_http_client_and_routes_notify_to_telegram():
    seen_requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append((request.method, request.url.path))
        return httpx.Response(200, json={"ok": True}, request=request)

    async def scenario():
        sched = Scheduler(gateway_base_url="http://127.0.0.1:8080")
        sched._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        r1 = await sched._execute_legacy({"kind": "notify", "text": "alert!"})
        r2 = await sched._execute_legacy({"kind": "http", "path": "/healthz"})
        assert r1["ok"] is True and r2["ok"] is True
        assert seen_requests == [("POST", "/notify/telegram"), ("GET", "/healthz")]
        client_ref = sched._http_client
        await sched.stop()
        assert sched._http_client is None
        assert client_ref.is_closed is True

    asyncio.run(scenario())


def test_scheduler_hhmm_persistence_and_router_validation(tmp_path: Path):
    persist_file = tmp_path / "dyn_jobs.json"
    sched = Scheduler(persist_path=persist_file)
    app = FastAPI()
    app.include_router(get_router({}, sched))
    client = TestClient(app)

    # Invalid schedule_time or negative interval returns 422
    assert client.post("/scheduler/jobs", json={"id": "bad_at", "at": "25:99"}).status_code == 422
    assert client.post("/scheduler/jobs", json={"id": "bad_int", "every_s": 0.1}).status_code == 422

    # Valid dynamic HH:MM job is normalized and persisted to JSON
    ok_resp = client.post(
        "/scheduler/jobs",
        json={"id": "morning_ping", "kind": "http", "path": "/healthz", "at": "7:05"},
    )
    assert ok_resp.status_code == 200
    assert ok_resp.json()["job"]["at"] == "07:05"
    assert persist_file.exists()

    reloaded = Scheduler(persist_path=persist_file)
    jobs = {j["id"]: j for j in reloaded.list_jobs()}
    assert "morning_ping" in jobs
    assert jobs["morning_ping"]["at"] == "07:05"

    wait_s = Scheduler._seconds_until_next_hhmm(8, 30, now=datetime(2026, 11, 16, 8, 15, 0))
    assert wait_s == 900.0
    assert Scheduler._seconds_until_next_hhmm(7, 0, now=datetime(2026, 11, 16, 8, 0, 0)) == 23 * 3600.0
