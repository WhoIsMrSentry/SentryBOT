"""Smoke tests for Agent Core module."""
import json


def test_validator_valid_json():
    from modules.agent_core.services.validator import LLMResponseValidator
    v = LLMResponseValidator()
    raw = json.dumps({
        "text": "Hello",
        "thoughts": "Testing",
        "actions": [{"type": "anim", "attrs": {"name": "blink"}}]
    })
    result = v.validate(raw)
    assert result["text"] == "Hello"
    assert isinstance(result["actions"], list)
    assert result.get("plan") == []


def test_validator_invalid_json():
    from modules.agent_core.services.validator import LLMResponseValidator
    v = LLMResponseValidator()
    result = v.validate("{broken json")
    assert result["text"] == "System error. Rebooting thought process."


def test_safety_filter_clamp_servo():
    from modules.agent_core.services.safety_filter import ActionSafetyFilter
    sf = ActionSafetyFilter({"safety": {"max_servo_angle": 180, "min_servo_angle": 0}})
    action = {"type": "servo", "attrs": {"pan": 999, "tilt": -50}}
    safe = sf.filter_action(action)
    assert safe["attrs"]["pan"] == 180
    assert safe["attrs"]["tilt"] == 0


def test_safety_filter_clamp_stepper():
    from modules.agent_core.services.safety_filter import ActionSafetyFilter
    sf = ActionSafetyFilter({"safety": {"max_stepper_speed": 100}})
    action = {"type": "stepper", "attrs": {"id": 0, "mode": "vel", "value": 200}}
    safe = sf.filter_action(action)
    assert safe["attrs"]["value"] == 100
    assert safe["attrs"]["id"] == 0
    assert safe["attrs"]["mode"] == "vel"


def test_planner_creates_steps():
    from modules.agent_core.services.planner import TaskPlanner
    p = TaskPlanner()
    queue = p.create_plan_queue(["navigate_to_door", "scan_environment"])
    assert len(queue) == 2
    assert queue[0]["objective"] == "navigate_to_door"
    assert queue[0]["status"] == "pending"
    assert queue[1]["step_id"] == 1


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
        "A": {"neighbors": ["B"]},
        "B": {"neighbors": ["A", "C"]},
        "C": {"neighbors": ["B"]},
    }
    s.current_location = "A"
    path = s.pathfind("C")
    assert path == ["A", "B", "C"]


def test_tool_registry_schema():
    from modules.agent_core.services.tools import ToolRegistry
    from modules.agent_core.services.world_state import WorldState
    from modules.agent_core.services.slam import TopologicalMap
    from modules.agent_core.services.memory import EpisodicMemory
    mem = EpisodicMemory(db_path=":memory:")
    slam = TopologicalMap.__new__(TopologicalMap)
    slam.map_file = "test_map_registry.json"
    slam.nodes = {}
    slam.current_location = "base"
    ws = WorldState()
    tr = ToolRegistry(mem, slam, ws)
    schema = tr.get_tool_schema()
    assert len(schema) == 4
    names = [t["function"]["name"] for t in schema]
    assert "search_memory" in names
    assert "get_battery" in names
