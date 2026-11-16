from __future__ import annotations

import logging
import threading
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.system_control.telemetry import config_loader
from modules.system_control.telemetry.api import router as telemetry_router
from modules.system_control.telemetry.services.metrics import (
    Registry,
    SystemSnapshot,
    read_system_snapshot,
)


def _client_for(cfg: dict, registry: Registry) -> TestClient:
    app = FastAPI()
    app.include_router(telemetry_router.get_router(cfg))
    return TestClient(app)


def test_telemetry_config_loader_applies_bind_host(monkeypatch) -> None:
    monkeypatch.setenv("TELEMETRY_HOST", "127.0.0.1")
    cfg = config_loader.load_config(None)
    assert cfg["server"]["host"] == "127.0.0.1"
    assert cfg["exporter"]["type"] == "builtin"


def test_telemetry_events_cardinality_cap_and_concurrent_render() -> None:
    reg = Registry(max_event_types=64)
    errors: list[Exception] = []

    def _worker(offset: int) -> None:
        try:
            for i in range(40):
                reg.record_event(f"evt_{offset}_{i}", latency_ms=float(i + 1))
        except Exception as exc:
            errors.append(exc)

    def _scraper() -> None:
        try:
            for _ in range(30):
                out = reg.render_prometheus()
                assert "events_total" in out or out == "\n"
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=_worker, args=(0,)),
        threading.Thread(target=_worker, args=(1,)),
        threading.Thread(target=_worker, args=(2,)),
        threading.Thread(target=_scraper),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert not errors
    snap = reg.snapshot()
    assert snap["tracked_event_types"] == 64
    assert snap["counters"]["events_total"] == 120.0
    assert snap["counters"]["event_other_total"] == float(120 - 64)


def test_telemetry_exporter_none_and_error_logging(monkeypatch, caplog) -> None:
    reg = Registry()
    monkeypatch.setattr(telemetry_router, "REGISTRY", reg)

    client = _client_for({"exporter": {"type": "none"}}, reg)
    hz = client.get("/telemetry/healthz")
    assert hz.status_code == 200
    assert hz.json()["exporter"] == "none"

    disabled = client.get("/telemetry/metrics")
    assert disabled.status_code == 503

    def _boom():
        raise RuntimeError("sensor unavailable")

    monkeypatch.setattr(telemetry_router, "read_system_snapshot", _boom)
    caplog.set_level(logging.DEBUG, logger="telemetry.router")
    builtin_client = _client_for({"exporter": {"type": "builtin"}}, reg)
    res = builtin_client.get("/telemetry/snapshot")
    assert res.status_code == 200
    assert any("host gauge refresh failed" in rec.message for rec in caplog.records)


def test_telemetry_summary_and_json_snapshot_endpoint(monkeypatch, tmp_path) -> None:
    reg = Registry()
    monkeypatch.setattr(telemetry_router, "REGISTRY", reg)
    monkeypatch.setattr(
        telemetry_router,
        "read_system_snapshot",
        lambda: SystemSnapshot(
            cpu_temp_c=48.2,
            cpu_load_1m=0.75,
            mem_available_mb=3200.5,
            disk_free_gb=12.4,
            disk_used_pct=38.0,
            pressure_level="normal",
        ),
    )

    client = _client_for({"exporter": {"type": "builtin"}}, reg)
    for ms in (10.0, 20.0, 30.0, 40.0, 100.0):
        ev = client.post("/telemetry/events", json={"type": "llm-turn", "latency_ms": ms})
        assert ev.status_code == 200
        assert ev.json()["metric"] == "event_llm_turn_total"

    snap_res = client.get("/telemetry/snapshot")
    assert snap_res.status_code == 200
    body = snap_res.json()
    assert body["ok"] is True
    assert body["host"]["mem_available_mb"] == 3200.5
    assert body["host"]["disk_free_gb"] == 12.4
    assert body["gauges"]["sentrybot_cpu_temp_c"] == 48.2
    assert body["gauges"]["sentrybot_disk_used_pct"] == 38.0
    assert body["counters"]["event_llm_turn_total"] == 5.0

    summary = body["summaries"]["event_llm_turn_latency_ms"]
    assert summary["count"] == 5
    assert summary["avg"] == 40.0
    assert summary["p50"] == 30.0
    assert summary["p95"] == 88.0
    assert summary["max"] == 100.0

    prom = client.get("/telemetry/metrics")
    assert prom.status_code == 200
    assert '# TYPE event_llm_turn_latency_ms summary' in prom.text
    assert 'event_llm_turn_latency_ms{quantile="0.95"} 88.0' in prom.text

    host_snap = read_system_snapshot(tmp_path)
    assert host_snap.disk_free_gb is not None
    assert host_snap.disk_used_pct is not None
