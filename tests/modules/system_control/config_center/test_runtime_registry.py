"""Tests for the runtime configuration registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.system_control.config_center.services.runtime_registry import RuntimeConfigRegistry
from modules.cognitive_memory.db import SocialDB


@pytest.fixture()
def social_db(tmp_path: Path) -> SocialDB:
    db = SocialDB(path=tmp_path / "social.sqlite3", wal=False)
    try:
        yield db
    finally:
        db.close()


def test_register_and_set_invokes_apply_fn(social_db: SocialDB) -> None:
    captured = {}

    def apply(value):
        captured["v"] = value
        return {"ok": True}

    reg = RuntimeConfigRegistry(social_db=social_db)
    reg.register(
        "vlm_bridge",
        "modes.depth",
        type="bool",
        default=False,
        description="Enable depth mode",
        apply_fn=apply,
    )
    out = reg.set("vlm_bridge", "modes.depth", "true", actor="tester")
    assert out["ok"] is True
    assert captured["v"] is True

    audit = reg.audit_log(limit=10)
    assert any(e["kind"] == "config.audit" for e in audit)
    last = audit[0]
    assert last["payload"]["key"] == "vlm_bridge.modes.depth"
    assert last["payload"]["new"] is True


def test_choice_validation(social_db: SocialDB) -> None:
    reg = RuntimeConfigRegistry(social_db=social_db)
    reg.register(
        "agent_core",
        "realtime_profile",
        type="choice",
        default="fast",
        choices=("fast", "normal"),
    )
    rejected = reg.set("agent_core", "realtime_profile", "ultra")
    assert rejected["ok"] is False
    assert "invalid_choice" in rejected["error"]
    accepted = reg.set("agent_core", "realtime_profile", "normal")
    assert accepted["ok"] is True


def test_numeric_bounds(social_db: SocialDB) -> None:
    reg = RuntimeConfigRegistry(social_db=social_db)
    reg.register(
        "agent_core",
        "max_subagents",
        type="int",
        default=2,
        minimum=1,
        maximum=4,
    )
    assert reg.set("agent_core", "max_subagents", 6)["ok"] is False
    assert reg.set("agent_core", "max_subagents", 3)["ok"] is True


def test_sensitive_redaction(social_db: SocialDB) -> None:
    reg = RuntimeConfigRegistry(social_db=social_db)
    reg.register(
        "vlm_bridge",
        "remote.auth_token",
        type="string",
        default="hidden",
        sensitive=True,
    )
    out = reg.list_keys(module="vlm_bridge")
    assert out[0]["value"] == "***"
    reg.set("vlm_bridge", "remote.auth_token", "real-secret")
    events = reg.audit_log(limit=5)
    assert events[0]["payload"]["new"] == "***"


def test_bulk_set(social_db: SocialDB) -> None:
    reg = RuntimeConfigRegistry(social_db=social_db)
    reg.register("vlm_bridge", "modes.ocr", type="bool", default=False)
    reg.register("vlm_bridge", "modes.faces", type="bool", default=True)
    results = reg.bulk_set({"vlm_bridge.modes.ocr": True, "vlm_bridge.modes.faces": False})
    assert all(r["ok"] for r in results)
    assert reg.get_value("vlm_bridge", "modes.ocr") is True
    assert reg.get_value("vlm_bridge", "modes.faces") is False
