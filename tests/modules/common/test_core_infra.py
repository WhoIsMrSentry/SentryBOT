"""Unit tests for core infrastructure fixes in modules.common."""

from __future__ import annotations

import asyncio
import sys
import threading
import time
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from modules.common import logger as common_logger
from modules.common import model_asset_truth, vision_availability
from modules.common.command_registry import (
    CommandRegistry,
    get_command_registry_async,
)
from modules.common.http_client import (
    AsyncHTTPClient,
    CircuitBreaker,
    close_all_clients,
    get_http_client,
)
from modules.common.job_types import (
    HTTPJobHandler,
    JobContext,
    JobDefinition,
    StateSetHandler,
    get_job_registry,
    get_job_registry_async,
)
from modules.common.persistence import JSONBackend, PersistenceConfig, SQLiteBackend
from modules.common.runtime_target import read_hardware_pressure, status as runtime_status
from modules.common.service_base import AsyncServiceBase, BackgroundTaskMixin, ServiceBase


# ---------------------------------------------------------------------------
# logger decoupling
# ---------------------------------------------------------------------------

def test_logger_register_log_provider_hooks(monkeypatch):
    monkeypatch.setitem(common_logger._LOG_PROVIDER, "init", None)
    monkeypatch.setitem(common_logger._LOG_PROVIDER, "memory_handler", None)
    monkeypatch.setitem(common_logger._LOG_PROVIDER, "router", None)

    calls = []
    sentinel_handler = object()
    sentinel_router = object()

    common_logger.register_log_provider(
        init_fn=lambda ov: calls.append(ov),
        memory_handler_fn=lambda: sentinel_handler,
        router_fn=lambda: sentinel_router,
    )

    common_logger.init_logging({"console_level": "DEBUG"})
    assert calls == [{"console_level": "DEBUG"}]
    assert common_logger.get_memory_handler() is sentinel_handler
    assert common_logger.get_router() is sentinel_router


# ---------------------------------------------------------------------------
# runtime_target hardware pressure
# ---------------------------------------------------------------------------

def test_read_hardware_pressure_levels(tmp_path: Path):
    thermal = tmp_path / "temp"
    meminfo = tmp_path / "meminfo"

    thermal.write_text("52000\n", encoding="utf-8")
    meminfo.write_text("MemTotal:        4096000 kB\nMemAvailable:    2048000 kB\n", encoding="utf-8")
    normal = read_hardware_pressure(thermal_path=thermal, meminfo_path=meminfo)
    assert normal["cpu_temp_c"] == 52.0
    assert normal["mem_available_mb"] == 2000.0
    assert normal["pressure_level"] == "normal"
    assert normal["eco_recommended"] is False

    thermal.write_text("74500\n", encoding="utf-8")
    warm = read_hardware_pressure(thermal_path=thermal, meminfo_path=meminfo)
    assert warm["pressure_level"] == "warm"
    assert warm["eco_recommended"] is True

    meminfo.write_text("MemAvailable:     102400 kB\n", encoding="utf-8")
    critical = read_hardware_pressure(thermal_path=thermal, meminfo_path=meminfo)
    assert critical["pressure_level"] == "critical"
    assert critical["eco_recommended"] is True


def test_runtime_status_includes_pressure():
    info = runtime_status()
    assert "pressure" in info
    assert info["pressure"]["pressure_level"] in {"normal", "warm", "critical"}


# ---------------------------------------------------------------------------
# vision_availability Session + TTL cache
# ---------------------------------------------------------------------------

def test_vision_availability_uses_ttl_cache_and_session():
    vision_availability.clear_vision_cache()
    fake_session = MagicMock()
    fake_session.get.return_value = MagicMock(status_code=200, json=lambda: {"ok": True, "gave_up": False})

    with patch.object(vision_availability, "_get_session", return_value=fake_session):
        assert vision_availability.camera_live_available("http://127.0.0.1:8080", cache_ttl_s=5.0) is True
        assert vision_availability.camera_live_available("http://127.0.0.1:8080", cache_ttl_s=5.0) is True
        assert fake_session.get.call_count == 1

        vision_availability.clear_vision_cache()
        assert vision_availability.camera_live_available("http://127.0.0.1:8080", cache_ttl_s=5.0) is True
        assert fake_session.get.call_count == 2


# ---------------------------------------------------------------------------
# model_asset_truth manifest sync & replacement
# ---------------------------------------------------------------------------

def test_model_asset_truth_manifest_sync_and_authoritative_override(tmp_path: Path):
    assert model_asset_truth.DEFAULT_MANIFEST["python_modules"]["piper"]["required"] is False
    assert "cv2" in model_asset_truth.DEFAULT_MANIFEST["python_modules"]
    assert "fastapi" in model_asset_truth.DEFAULT_MANIFEST["python_modules"]
    assert "uvicorn" in model_asset_truth.DEFAULT_MANIFEST["python_modules"]
    assert "rpicam-hello" in model_asset_truth.DEFAULT_MANIFEST["commands"]

    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "model_assets.json").write_text(
        '{"assets": {}, "python_modules": {"json": {"required": true, "purpose": "stdlib"}}, "commands": {}}',
        encoding="utf-8",
    )
    loaded = model_asset_truth._load_manifest(tmp_path)
    assert loaded["assets"] == {}
    assert list(loaded["python_modules"].keys()) == ["json"]
    assert loaded["commands"] == {}


# ---------------------------------------------------------------------------
# persistence SQLite GLOB & JSON atomic locked writes
# ---------------------------------------------------------------------------

def test_sqlite_backend_keys_glob(tmp_path: Path):
    cfg = PersistenceConfig(backend="sqlite", path=str(tmp_path / "kv.db"))
    with SQLiteBackend(cfg) as store:
        store.set("user:1", "alice")
        store.set("user:2", "bob")
        store.set("userx", "other")
        store.set("session:1", "tok")

        assert store.keys("user:*") == ["user:1", "user:2"]
        assert store.keys("user:?") == ["user:1", "user:2"]
        assert store.keys("*") == ["session:1", "user:1", "user:2", "userx"]


def test_json_backend_thread_safe_atomic_save(tmp_path: Path):
    target = tmp_path / "state.json"
    cfg = PersistenceConfig(backend="json", path=str(target), auto_save=False)
    store = JSONBackend(cfg)

    def writer(start: int) -> None:
        for i in range(start, start + 15):
            store.set(f"k:{i}", i)
            store._save()

    threads = [threading.Thread(target=writer, args=(idx * 100,)) for idx in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    store.close()
    reloaded = JSONBackend(cfg)
    assert len(reloaded.keys("*")) == 60
    leftover_tmps = list(tmp_path.glob("*.tmp"))
    assert leftover_tmps == []


# ---------------------------------------------------------------------------
# service_base lifecycle & BackgroundTaskMixin
# ---------------------------------------------------------------------------

class _DummySyncService(ServiceBase):
    def _do_initialize(self) -> None:
        pass

    def _do_start(self) -> None:
        pass

    def _do_stop(self, timeout: float) -> None:
        pass


class _DummyAsyncService(AsyncServiceBase, BackgroundTaskMixin):
    def __init__(self):
        AsyncServiceBase.__init__(self, name="dummy_async")
        BackgroundTaskMixin.__init__(self)

    async def _do_initialize(self) -> None:
        pass

    async def _do_start(self) -> None:
        pass

    async def _do_stop(self, timeout: float) -> None:
        await self.cancel_background_tasks()


def test_sync_service_stops_and_joins_health_thread():
    svc = _DummySyncService(config={"health_check_interval": 30.0}, name="hc_test")
    svc.start()
    assert svc._health_check_task is not None
    assert svc._health_check_task.is_alive()

    t0 = time.monotonic()
    svc.stop()
    elapsed = time.monotonic() - t0
    assert elapsed < 1.5
    assert svc._health_check_task is None
    assert svc.is_stopped is True


def test_async_service_and_background_task_factory():
    # Must be instantiable before an asyncio loop is active
    svc = _DummyAsyncService()

    async def scenario():
        await svc.start()

        async def bad_once():
            raise RuntimeError("boom")

        with pytest.raises(TypeError):
            await svc.create_background_task(bad_once(), restart=True)

        attempts = 0

        async def flaky_job():
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                raise RuntimeError("retry me")
            return "ok"

        task = await svc.create_background_task(flaky_job, name="flaky", restart=True, restart_delay=0.01)
        result = await task
        assert result == "ok"
        assert attempts == 2
        await svc.stop()

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# http_client breaker isolation, 4xx non-trip & shutdown
# ---------------------------------------------------------------------------

def test_http_client_breaker_isolation_and_4xx_handling():
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.02, half_open_max_calls=1)
    assert breaker.can_execute("svc") is True
    breaker.record_failure("svc")
    breaker.record_failure("svc")
    assert breaker.snapshot_states()["svc"] == "open"
    assert breaker.can_execute("svc") is False
    time.sleep(0.03)
    assert breaker.can_execute("svc") is True
    assert breaker.snapshot_states()["svc"] == "half-open"
    breaker.record_success("svc")
    assert breaker.snapshot_states()["svc"] == "closed"

    client = AsyncHTTPClient("http://127.0.0.1:8080")
    assert client._extract_host("/speech/status") == "127.0.0.1:8080/speech"
    assert client._extract_host("/camera/snap") == "127.0.0.1:8080/camera"
    assert client._extract_host("http://10.0.0.5:9000/v1/chat") == "10.0.0.5:9000"

    async def scenario():
        calls = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if request.url.path == "/speech/missing":
                return httpx.Response(404, request=request)
            return httpx.Response(200, json={"ok": True}, request=request)

        client._client = httpx.AsyncClient(
            base_url=client.base_url,
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(httpx.HTTPStatusError):
            await client.get("/speech/missing")

        # Non-429 4xx must not retry and must not increment circuit-breaker failures
        assert calls == 1
        assert client.circuit_breaker.snapshot_states().get("127.0.0.1:8080/speech", "closed") == "closed"

        ok_resp = await client.get("/camera/snap")
        assert ok_resp.status_code == 200
        await client.close()

    asyncio.run(scenario())


def test_http_client_close_all_clients():
    async def scenario():
        c1 = get_http_client("http://127.0.0.1:18080", timeout=2.0)
        assert c1 is get_http_client("http://127.0.0.1:18080", timeout=2.0)
        await close_all_clients()
        c2 = get_http_client("http://127.0.0.1:18080", timeout=2.0)
        assert c2 is not c1
        await close_all_clients()

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# job_types sync/async registry, HTTP session reuse & StateSetHandler
# ---------------------------------------------------------------------------

def test_job_registry_and_handlers(monkeypatch):
    assert get_job_registry() is asyncio.run(get_job_registry_async())

    class _SyncStateStore:
        def __init__(self):
            self.items = {}

        def set_value(self, key: str, value):
            self.items[key] = value

    store = _SyncStateStore()
    state_ctx = JobContext(
        JobDefinition(id="j1", kind="state_set", params={"key": "mood", "value": "happy"}),
        {"state_manager": store},
    )
    out = asyncio.run(StateSetHandler().execute(state_ctx))
    assert out["set"] is True
    assert store.items["mood"] == "happy"

    class _FakeResp:
        status = 200
        headers = {"Content-Type": "application/json"}

        async def json(self):
            return {"ok": True}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class _FakeSession:
        def __init__(self):
            self.calls = []
            self.closed = False

        def request(self, method, url, **kwargs):
            self.calls.append((method, url))
            return _FakeResp()

        async def close(self):
            self.closed = True

    fake_aiohttp = types.SimpleNamespace(
        ClientTimeout=lambda total: total,
        ClientSession=MagicMock(side_effect=AssertionError("should reuse injected session")),
    )
    monkeypatch.setitem(sys.modules, "aiohttp", fake_aiohttp)

    session = _FakeSession()
    http_ctx = JobContext(
        JobDefinition(id="j2", kind="http", params={"path": "/health", "method": "get"}),
        {"gateway_base_url": "http://127.0.0.1:8080/", "_aiohttp_session": session},
    )
    http_res = asyncio.run(HTTPJobHandler().execute(http_ctx))
    assert http_res["status"] == 200
    assert http_res["json"] == {"ok": True}
    assert session.calls == [("GET", "http://127.0.0.1:8080/health")]
    assert session.closed is False


# ---------------------------------------------------------------------------
# command_registry async lock fix, injection & shared HTTP handler
# ---------------------------------------------------------------------------

def test_command_registry_async_and_http_handlers():
    async def scenario():
        reg = await get_command_registry_async()
        assert reg is not None

        seen = {}
        custom_calls = []

        class _EchoUser:
            name = "whoami"
            usage = "/whoami"
            description = "Who am I"

            async def execute(self, ctx):
                custom_calls.append(ctx.username)
                from modules.common.command_registry import CommandResult

                return CommandResult(text=f"user:{ctx.username}")

        local_reg = CommandRegistry(base_url="http://127.0.0.1:8080")
        local_reg.register(_EchoUser())

        async def transport_handler(request: httpx.Request) -> httpx.Response:
            seen[request.url.path] = dict(request.url.params)
            if request.url.path == "/health":
                return httpx.Response(200, json={"ok": True, "speech": {"ok": True}}, request=request)
            if request.url.path == "/vlm/track":
                return httpx.Response(200, json={"ok": True}, request=request)
            if request.url.path == "/speak/say":
                return httpx.Response(
                    200,
                    json={"ok": True},
                    headers={"content-type": "application/json"},
                    request=request,
                )
            return httpx.Response(404, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(transport_handler)) as client:
            local_reg.set_http_client(client)

            help_text = await local_reg.handle("/help")
            assert help_text and "/status" in help_text

            who = await local_reg.handle("/whoami", user_id=7, username="emre")
            assert who == "user:emre"
            assert custom_calls == ["emre"]

            status_text = await local_reg.handle("/status")
            assert "Durum ok" in status_text and "speech:ok" in status_text

            pan_text = await local_reg.handle("pan 15")
            assert pan_text == "Pan ok"
            assert seen["/vlm/track"] == {"head_pan": "15.0", "head_tilt": "0.0"}

            say_text = await local_reg.handle("/say merhaba dunya")
            assert say_text == "TTS oynatılıyor"

    asyncio.run(scenario())
