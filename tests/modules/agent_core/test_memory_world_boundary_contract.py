from __future__ import annotations

from modules.agent_core.services import memory, memory_consolidator, world_state


def test_memory_world_boundary_contract_markers_present():
    assert memory.MEMORY_WORLD_COMPATIBILITY is True
    assert memory_consolidator.MEMORY_WORLD_COMPATIBILITY is True
    assert world_state.MEMORY_WORLD_COMPATIBILITY is True

    assert memory.MEMORY_WORLD_RUNTIME_OWNER == "modules.autonomy.services.world_memory"
    assert memory_consolidator.MEMORY_WORLD_RUNTIME_OWNER == "modules.autonomy.services.world_memory"
    assert world_state.MEMORY_WORLD_RUNTIME_OWNER == "modules.autonomy.services.world_memory"


def test_memory_world_public_classes_remain_exported():
    assert hasattr(memory, "EpisodicMemory")
    assert hasattr(memory_consolidator, "MemoryConsolidator")
    assert hasattr(world_state, "WorldState")
