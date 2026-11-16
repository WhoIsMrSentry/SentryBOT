"""Persistence, concurrency, API validation, and SSE stream tests for state_manager."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi import FastAPI
from starlette.testclient import TestClient

from modules.system_control.state_manager.api.router import get_router
from modules.system_control.state_manager.services.store import StateStore


def test_sqlite_persistence_concurrent_writes_and_close(tmp_path: Path):
    db_path = tmp_path / "state.sqlite3"
    store = StateStore(
        defaults={"operational": "idle", "emotions": []},
        persistence={"type": "sqlite", "path": str(db_path)},
    )

    errors = []

    def worker(idx: int) -> None:
        try:
            for step in range(15):
                store.set_value(f"k_{idx}_{step}", step)
                if step % 5 == 0:
                    store.update({f"u_{idx}": step})
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    store.set_operational("active")
    store.set_emotions(["joy", "curious"])
    store.close()
    # Idempotent close
    store.close()

    reloaded = StateStore(
        defaults={"operational": "idle", "emotions": []},
        persistence={"type": "sqlite", "path": str(db_path)},
    )
    try:
        snap = reloaded.get()
        assert snap["operational"] == "active"
        assert snap["emotions"] == ["joy", "curious"]
        assert snap["k_3_14"] == 14
    finally:
        reloaded.close()


def test_json_persistence_atomic_writes(tmp_path: Path):
    json_path = tmp_path / "state.json"
    store = StateStore(
        defaults={"operational": "idle", "emotions": []},
        persistence={"type": "json", "path": str(json_path)},
    )
    store.set_value("battery", 88)
    assert list(tmp_path.glob("*.tmp")) == []

    reloaded = StateStore(
        defaults={"operational": "idle", "emotions": []},
        persistence={"type": "json", "path": str(json_path)},
    )
    assert reloaded.get("battery") == 88


def test_state_router_get_key_operational_validation_and_sse(tmp_path: Path):
    store = StateStore(
        defaults={"operational": "idle", "emotions": [], "temp": 42},
        persistence={"type": "sqlite", "path": str(tmp_path / "http_state.sqlite3")},
    )
    try:
        app = FastAPI()
        app.include_router(get_router(store))
        client = TestClient(app)

        assert client.get("/state/get", params={"key": "temp"}).json() == {"temp": 42}
        assert client.get("/state/get", params={"key": "does_not_exist"}).status_code == 404

        assert client.post("/state/set/operational", json={"value": "listening"}).status_code == 200
        assert client.get("/state/get", params={"key": "operational"}).json() == {"operational": "listening"}
        assert client.post("/state/set/operational", json={"value": "totally_invalid"}).status_code == 400

        # SSE /state/stream emits initial snapshot + state event on update
        def _delayed_update() -> None:
            time.sleep(0.05)
            store.set_operational("active")

        updater = threading.Thread(target=_delayed_update)
        updater.start()
        with client.stream("GET", "/state/stream", params={"max_events": 2, "heartbeat_s": 1.0}) as resp:
            assert resp.status_code == 200
            body = "".join(resp.iter_text())
        updater.join(timeout=2.0)

        assert "event: snapshot" in body
        assert "event: state" in body
        assert '"operational"' in body
        assert '"active"' in body
    finally:
        store.close()
