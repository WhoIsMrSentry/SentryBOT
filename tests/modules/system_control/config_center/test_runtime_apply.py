"""YAML -> runtime registry bridge helpers."""

from __future__ import annotations

from pathlib import Path

from modules.system_control.config_center.services.runtime_registry import RuntimeConfigRegistry
from modules.system_control.config_center.services.yaml_runtime_apply import apply_module_yaml
from modules.cognitive_memory.db import SocialDB


def test_yaml_apply_vlm_processing_mode(tmp_path: Path):
    captured = {}

    def apply_fn(value):
        captured["processing"] = value
        return {"ok": True}

    db = SocialDB(path=tmp_path / "audit.sqlite3", wal=False)
    reg = RuntimeConfigRegistry(social_db=db)
    reg.register("vlm_bridge", "vision.processing_mode", type="string", apply_fn=apply_fn)
    summary = apply_module_yaml(
        reg,
        "vlm_bridge",
        {"vision": {"processing_mode": "remote"}},
    )
    assert "vlm_bridge.vision.processing_mode" in summary.get("applied", [])
    assert captured.get("processing") == "remote"
