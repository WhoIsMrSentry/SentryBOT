from __future__ import annotations

from pathlib import Path

from modules.autonomy.services.world_memory import WorldMemory


def test_world_memory_persists_across_instances(tmp_path: Path):
    path = tmp_path / "world_memory.json"
    cfg = {"storage_path": str(path), "persistence_enabled": True}
    first = WorldMemory(cfg)
    observed = first.observe({"kind": "object", "name": "persistent cube", "summary": "cube on desk", "source": "test"}, now=1.0)
    assert observed["ok"] is True
    assert path.exists()
    second = WorldMemory(cfg)
    recent = second.recent(kind="objects", limit=5)
    assert second.status()["persistence"]["loaded"] is True
    assert recent["count"] == 1
    assert recent["items"][0]["name"] == "persistent cube"


def test_world_memory_persistence_can_be_disabled(tmp_path: Path):
    path = tmp_path / "disabled.json"
    mem = WorldMemory({"storage_path": str(path), "persistence_enabled": False})
    mem.observe({"kind": "object", "name": "not written"})
    assert path.exists() is False
    assert mem.status()["persistence"]["enabled"] is False


def test_world_memory_clear_is_persisted(tmp_path: Path):
    path = tmp_path / "world_memory.json"
    cfg = {"storage_path": str(path), "persistence_enabled": True}
    mem = WorldMemory(cfg)
    mem.observe({"kind": "person", "name": "owner"}, now=1.0)
    mem.clear(kind="people")
    loaded = WorldMemory(cfg)
    assert loaded.status()["counts"]["people"] == 0



def test_non_persistent_instances_do_not_read_storage(tmp_path: Path):
    path = tmp_path / "world_memory.json"
    seeded = WorldMemory({"storage_path": str(path), "persistence_enabled": True})
    seeded.observe({"kind": "object", "name": "runtime-only object"}, now=1.0)
    isolated = WorldMemory({"storage_path": str(path), "persistence_enabled": False})
    assert isolated.status()["persistence"]["enabled"] is False
    assert isolated.recent(kind="objects")["count"] == 0
