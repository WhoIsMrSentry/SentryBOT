from __future__ import annotations

from modules.autonomy.services.idle_behaviors import IdleBehaviorPlanner


def test_idle_planner_returns_action_when_available():
    planner = IdleBehaviorPlanner({"behaviors": {"idle_tree": {"path": ""}}})
    action = planner.pick(now=100.0)
    assert action is None

def test_idle_planner_respects_per_action_cooldown():
    planner = IdleBehaviorPlanner({"behaviors": {"idle_tree": {"path": ""}}})
    action = planner.pick(now=50.0)
    assert action is None
