from __future__ import annotations

from modules.cognitive_memory.services.world_memory import (
    WORLD_MEMORY_PERSISTENCE_TRUTH_CONTRACT,
    WORLD_MEMORY_PERSISTENCE_ROLE,
    WorldMemory,
)


def test_world_memory_reports_real_local_persistence_status(tmp_path):
    path = tmp_path / "world_memory.json"
    memory = WorldMemory({"storage_path": str(path), "persistence_enabled": True})
    assert WORLD_MEMORY_PERSISTENCE_TRUTH_CONTRACT is True
    assert WORLD_MEMORY_PERSISTENCE_ROLE == "local_json_semantic_memory_store"
    status = memory.status()
    assert status["persistence"]["enabled"] is True
    assert status["persistence"]["path"] == str(path)
    assert status["persistence"]["exists"] is False
    memory.observe({"kind": "person", "name": "Emir"}, source="test", now=1.0)
    status_after = memory.status()
    assert status_after["persistence"]["exists"] is True
    assert status_after["persistence"]["error"] == ""


def test_world_memory_disabled_persistence_is_reported_without_disk_write(tmp_path):
    path = tmp_path / "world_memory_disabled.json"
    memory = WorldMemory({"storage_path": str(path), "persistence_enabled": False})
    memory.observe({"kind": "object", "name": "cup"}, source="test", now=1.0)
    status = memory.status()
    assert status["total"] == 1
    assert status["persistence"]["enabled"] is False
    assert status["persistence"]["exists"] is False
    assert not path.exists()
