from __future__ import annotations

from modules.autonomy.services.idle_behaviors import IdleBehaviorPlanner


def test_idle_planner_returns_action_when_available():
    planner = IdleBehaviorPlanner({"behaviors": {"idle_tree": {"path": ""}}})
    action = planner.pick(now=100.0)
    assert action is not None
    assert bool(action.name)


def test_idle_planner_respects_per_action_cooldown():
    planner = IdleBehaviorPlanner({"behaviors": {"idle_tree": {"path": ""}}})
    action = planner.pick(now=50.0)
    assert action is not None
    planner.stamp(action.name, now=50.0)
    # Immediately after stamp, same action should not be eligible until its own cooldown.
    blocked = planner.pick(now=50.1)
    # There may be other actions available; ensure if a pick happens it is not the same action.
    if blocked is not None:
        assert blocked.name != action.name
