"""Comprehensive API, discovery, rollback, atomic write, and registry tests for config_center."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import yaml
from fastapi import FastAPI
from starlette.testclient import TestClient

from modules.system_control.config_center.api.router import get_router
from modules.system_control.config_center.config_loader import load_config
from modules.system_control.config_center.services.runtime_registry import (
    RuntimeConfigRegistry,
    get_default_registry,
    set_default_registry,
)
from modules.system_control.config_center.services.yaml_runtime_apply import apply_module_yaml


def test_config_center_config_yml_port_and_paths_valid():
    cfg = load_config()
    assert int(cfg["server"]["port"]) != 8099
    modules = cfg["modules"]
    names = [m["name"] for m in modules]
    assert len(names) == len(set(names))
    repo_root = Path(__file__).resolve().parents[4]
    for item in modules:
        p = (repo_root / item["path"]).resolve()
        assert p.is_file(), f"Missing config file referenced in config_center: {item}"


def test_config_get_raw_dry_run_backup_rotation_and_rollback():
    target_dir = Path("data") / "_test_cfg_center_tmp"
    repo_root = Path(__file__).resolve().parents[4]
    work_dir = repo_root / target_dir
    work_dir.mkdir(parents=True, exist_ok=True)
    mod_file = work_dir / "config.yml"
    mod_file.write_text("brightness: 10\n", encoding="utf-8")

    try:
        reg = RuntimeConfigRegistry(social_db=None)
        applied_values = []
        reg.register(
            "dummy_mod",
            "brightness",
            type="int",
            default=10,
            apply_fn=lambda v: applied_values.append(v) or {"ok": True},
        )

        cfg = {
            "modules": [
                {"name": "dummy_mod", "path": f"{target_dir.as_posix()}/config.yml"},
                {"name": "escaped_mod", "path": "../../../etc/passwd"},
            ]
        }
        app = FastAPI()
        app.include_router(get_router(cfg, registry=reg))
        client = TestClient(app)

        # Headless without static/index.html -> /config/ui is not mounted
        assert client.get("/config/ui").status_code == 404

        # repo_root resolution works for /get and /raw
        r_get = client.get("/config/get", params={"module": "dummy_mod"})
        assert r_get.status_code == 200
        assert r_get.json()["brightness"] == 10

        r_raw = client.get("/config/raw", params={"module": "dummy_mod"})
        assert r_raw.status_code == 200
        assert "brightness: 10" in r_raw.text

        # Path traversal outside repo blocked
        assert client.get("/config/get", params={"module": "escaped_mod"}).status_code == 403

        # dry_run validates YAML without writing disk or creating backups
        r_dry = client.put(
            "/config/set",
            params={"module": "dummy_mod", "dry_run": "true"},
            content="brightness: 42\n",
            headers={"content-type": "text/plain"},
        )
        assert r_dry.status_code == 200
        assert r_dry.json()["dry_run"] is True
        assert applied_values == []
        assert mod_file.read_text(encoding="utf-8") == "brightness: 10\n"
        assert list(work_dir.glob("config.yml.bak-*")) == []

        # Invalid non-mapping root rejected with 400
        r_bad = client.put(
            "/config/set",
            params={"module": "dummy_mod", "dry_run": "true"},
            content="- just_a_list\n",
            headers={"content-type": "text/plain"},
        )
        assert r_bad.status_code == 400

        # Multiple writes rotate backups to max 5 files
        for idx in range(1, 8):
            r_put = client.put(
                "/config/set",
                params={"module": "dummy_mod", "apply_runtime": "false"},
                content=f"brightness: {10 + idx}\n",
                headers={"content-type": "text/plain"},
            )
            assert r_put.status_code == 200
            time.sleep(0.002)

        backups = sorted(work_dir.glob("config.yml.bak-*"), reverse=True)
        assert len(backups) == 5

        # Rollback restores latest backup (brightness: 16 before last write 17)
        r_rb = client.post("/config/rollback", params={"module": "dummy_mod"})
        assert r_rb.status_code == 200
        assert r_rb.json()["ok"] is True
        restored = yaml.safe_load(mod_file.read_text(encoding="utf-8"))
        assert restored["brightness"] == 16
    finally:
        for f in work_dir.glob("*"):
            f.unlink(missing_ok=True)
        for f in work_dir.glob(".*"):
            if f.is_file():
                f.unlink(missing_ok=True)
        work_dir.rmdir()


def test_config_scan_discovers_nested_modules(monkeypatch):
    persisted = []
    monkeypatch.setattr(
        "modules.system_control.config_center.api.scan.persist_modules_if_possible",
        lambda mods, cfg_path, lock=None: persisted.append((len(mods), str(cfg_path))),
    )
    app = FastAPI()
    app.include_router(get_router({"modules": []}))
    client = TestClient(app)

    res = client.post("/config/scan")
    assert res.status_code == 200
    payload = res.json()
    assert payload["ok"] is True
    assert persisted and persisted[0][0] == payload["total"]
    names = {item["name"] for item in payload["added"]}
    # Verify nested modules at depth 2+ are found cleanly
    assert {"speak", "neopixel", "state_manager", "config_center"}.issubset(names)


def test_runtime_registry_bool_validation_and_non_blocking_reads():
    gate = threading.Event()
    entered = threading.Event()

    def slow_apply(val):
        entered.set()
        gate.wait(timeout=2.0)
        return {"ok": True, "applied": val}

    reg = RuntimeConfigRegistry(social_db=None)
    reg.register("mod", "flag", type="bool", default=False, apply_fn=slow_apply)

    assert reg.set("mod", "flag", "invalid-bool")["ok"] is False

    writer = threading.Thread(target=lambda: reg.set("mod", "flag", "true"))
    writer.start()
    assert entered.wait(timeout=1.0)

    # Reader must not stall waiting for slow apply_fn
    t0 = time.monotonic()
    assert reg.get_value("mod", "flag") is False
    elapsed = time.monotonic() - t0
    assert elapsed < 0.5

    gate.set()
    writer.join(timeout=2.0)
    assert reg.get_value("mod", "flag") is True


def test_yaml_runtime_apply_multi_module_and_dynamic_registry():
    reg = RuntimeConfigRegistry(social_db=None)
    reg.register("neopixel", "brightness", type="float", default=0.5)
    reg.register("speak", "tts.rate", type="int", default=170)

    res1 = apply_module_yaml(reg, "neopixel", {"brightness": 0.8})
    assert "neopixel.brightness" in res1["applied"]
    assert res1["cache_cleared"] is True

    res2 = apply_module_yaml(reg, "speak", {"tts": {"rate": 195}})
    assert "speak.tts.rate" in res2["applied"]

    # Dynamic registry provider in router picks up late set_default_registry
    prev = get_default_registry()
    try:
        app = FastAPI()
        app.include_router(get_router({"modules": []}))
        client = TestClient(app)
        set_default_registry(reg)
        keys_resp = client.get("/config/runtime/list")
        assert keys_resp.status_code == 200
        assert any(k["module"] == "neopixel" for k in keys_resp.json()["keys"])
    finally:
        if prev is not None:
            set_default_registry(prev)
