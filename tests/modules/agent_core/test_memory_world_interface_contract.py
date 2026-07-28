from __future__ import annotations

import inspect

from modules.agent_core.services.memory import EpisodicMemory
from modules.agent_core.services.memory_consolidator import MemoryConsolidator
from modules.agent_core.services.world_state import WorldState


EXPECTED_SIGNATURES = {'EpisodicMemory.__init__': '(self, db_path: str = None)',
 'EpisodicMemory.remember': '(self, event_type: str, content: str, importance: int = 1)',
 'EpisodicMemory.search_memory': '(self, query: str, limit: int = 5) -> List[Dict[str, Any]]',
 'MemoryConsolidator.__init__': "(self, memory: 'Any' = None, social_db: 'Any' = None, learner: 'Any' = None, autonomy_client: 'Any' = None, world_memory: 'Any' = None, llm_client: 'Any' = None, enabled: 'bool' = True) -> 'None'",
 'MemoryConsolidator.consolidate': "(self, text: 'str', speaker: 'Optional[str]' = None) -> "
                                   "'List[str]'",
 'MemoryConsolidator.extract_facts': "(self, text: 'str', speaker: 'Optional[str]' = None) -> 'List[str]'",
 'WorldState.__init__': '(self)',
 'WorldState.get_state': '(self) -> Dict[str, Any]',
 'WorldState.inject_world_state': '(self, base_prompt: str) -> str',
 'WorldState.set_action_feedback': '(self, feedback: str)',
 'WorldState.update_scene': '(self, context: Dict[str, Any]) -> None',
 'WorldState.update_state': '(self, updates: Dict[str, Any])'}
MEMORY_PROBE = {'error': '',
 'ok': True,
 'remember_return_type': 'NoneType',
 'search_item_keys': ['content', 'time', 'type'],
 'search_item_type': 'dict',
 'search_len': 1,
 'search_result_type': 'list'}
WORLD_STATE_PROBE = {'after_type': 'dict',
 'error': '',
 'initial_type': 'dict',
 'inject_contains_marker': True,
 'inject_type': 'str',
 'ok': True,
 'updated_keys_that_roundtrip': {'battery_percent': 55, 'speaker': 'contract_speaker_145'}}


def _make_memory() -> EpisodicMemory:
    try:
        return EpisodicMemory(db_path=":memory:")
    except TypeError:
        return EpisodicMemory()


def test_agent_core_memory_world_signatures_are_stable():
    actual = {
        "EpisodicMemory.__init__": str(inspect.signature(EpisodicMemory.__init__)),
        "EpisodicMemory.remember": str(inspect.signature(EpisodicMemory.remember)),
        "EpisodicMemory.search_memory": str(inspect.signature(EpisodicMemory.search_memory)),
        "MemoryConsolidator.__init__": str(inspect.signature(MemoryConsolidator.__init__)),
        "MemoryConsolidator.consolidate": str(inspect.signature(MemoryConsolidator.consolidate)),
        "MemoryConsolidator.extract_facts": str(inspect.signature(MemoryConsolidator.extract_facts)),
        "WorldState.__init__": str(inspect.signature(WorldState.__init__)),
        "WorldState.get_state": str(inspect.signature(WorldState.get_state)),
        "WorldState.update_state": str(inspect.signature(WorldState.update_state)),
        "WorldState.update_scene": str(inspect.signature(WorldState.update_scene)),
        "WorldState.inject_world_state": str(inspect.signature(WorldState.inject_world_state)),
        "WorldState.set_action_feedback": str(inspect.signature(WorldState.set_action_feedback)),
    }
    assert actual == EXPECTED_SIGNATURES


def test_episodic_memory_current_return_shape_contract():
    mem = _make_memory()
    marker = "contract_unique_alpha_145"
    remembered = mem.remember("dialogue", f"User: {marker} | Bot: contract response")
    assert type(remembered).__name__ == MEMORY_PROBE["remember_return_type"]

    results = mem.search_memory(marker, 5)
    assert type(results).__name__ == MEMORY_PROBE["search_result_type"]

    if MEMORY_PROBE["search_result_type"] == "list":
        assert isinstance(results, list)
        if MEMORY_PROBE["search_len"] > 0:
            assert len(results) > 0
            assert type(results[0]).__name__ == MEMORY_PROBE["search_item_type"]
            if MEMORY_PROBE["search_item_type"] == "dict":
                assert set(MEMORY_PROBE["search_item_keys"]).issubset(set(results[0].keys()))


def test_world_state_current_return_shape_contract():
    ws = WorldState()
    initial = ws.get_state()
    assert type(initial).__name__ == WORLD_STATE_PROBE["initial_type"]

    payload = {"speaker": "contract_speaker_145", "battery_percent": 55}
    ws.update_state(payload)
    after = ws.get_state()
    assert type(after).__name__ == WORLD_STATE_PROBE["after_type"]

    for key, value in WORLD_STATE_PROBE["updated_keys_that_roundtrip"].items():
        assert after.get(key) == value

    injected = ws.inject_world_state("BASE_PROMPT_145")
    assert type(injected).__name__ == WORLD_STATE_PROBE["inject_type"]
    if WORLD_STATE_PROBE["inject_contains_marker"]:
        assert "SYSTEM WORLD STATE" in injected
        assert "BASE_PROMPT_145" in injected
