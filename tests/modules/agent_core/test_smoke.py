"""Smoke tests for Agent Core native tool calling module."""
import json
import pytest

def test_safety_filter_clamp_servo():
    from modules.agent_core.services.safety_filter import ActionSafetyFilter
    sf = ActionSafetyFilter({"safety": {"max_servo_angle": 180, "min_servo_angle": 0}})
    
    pan = sf.clamp_servo(999)
    tilt = sf.clamp_servo(-50)
    
    assert pan == 180
    assert tilt == 0


def test_safety_filter_clamp_stepper():
    from modules.agent_core.services.safety_filter import ActionSafetyFilter
    sf = ActionSafetyFilter({"safety": {"max_stepper_speed": 100}})
    
    speed1 = sf.clamp_stepper(200)
    speed2 = sf.clamp_stepper(-150)
    
    assert speed1 == 100
    assert speed2 == -100


def test_world_state_injection():
    from modules.agent_core.services.world_state import WorldState
    ws = WorldState()
    ws.update_state({"battery_percent": 42})
    injected = ws.inject_world_state("")
    assert "42" in injected
    assert "WORLD STATE" in injected


def test_memory_crud():
    from modules.agent_core.services.memory import EpisodicMemory
    m = EpisodicMemory(db_path=":memory:")
    m.remember("dialogue", "Hello world", importance=5)
    results = m.search_memory("Hello")
    assert len(results) == 1
    assert "Hello world" in results[0]["content"]


def test_slam_pathfind():
    from modules.agent_core.services.slam import TopologicalMap
    s = TopologicalMap.__new__(TopologicalMap)
    s.map_file = "test_map.json"
    s.nodes = {
        "a": {"neighbors": ["b"]},
        "b": {"neighbors": ["a", "c"]},
        "c": {"neighbors": ["b"]},
    }
    s.aliases = {}
    s.current_location = "a"
    path = s.pathfind("c")
    assert path == ["a", "b", "c"]


def test_tool_registry_schemas():
    from modules.agent_core.services.tools import ToolRegistry
    from modules.agent_core.services.world_state import WorldState
    from modules.agent_core.services.slam import TopologicalMap
    from modules.agent_core.services.memory import EpisodicMemory
    from modules.agent_core.services.safety_filter import ActionSafetyFilter

    mem = EpisodicMemory(db_path=":memory:")
    slam = TopologicalMap.__new__(TopologicalMap)
    slam.map_file = "test_map_registry.json"
    slam.nodes = {}
    slam.aliases = {}
    slam.current_location = "base"
    ws = WorldState()
    sf = ActionSafetyFilter()
    
    # We pass None for client to test schema generation safely
    tr = ToolRegistry(None, mem, slam, ws, sf)
    schema = tr.get_tool_schema()
    
    # Living Vision Agent added new tools; verify minimum count
    assert len(schema) >= 15
    names = [t["function"]["name"] for t in schema]
    
    # Verify core tools are present
    assert "move_head" in names
    assert "play_sound" in names
    assert "set_lights" in names
    assert "set_laser" not in names
    assert "oled_face" in names
    assert "search_memory" in names
    assert "get_vision" in names
    assert "get_sensor_data" in names
    assert "get_location" in names
    assert "pathfind" in names

    filtered = tr.get_tool_schema(include=["move_head", "search_memory", "unknown_tool"])
    filtered_names = [t["function"]["name"] for t in filtered]
    assert filtered_names == ["move_head", "search_memory"]
