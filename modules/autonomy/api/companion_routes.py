from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter

from ..services.brain import AutonomyBrain


def register_companion_routes(router: APIRouter, brain: AutonomyBrain) -> None:
    @router.get("/needs")
    def get_needs():
        if hasattr(brain, "get_needs_snapshot"):
            return brain.get_needs_snapshot()
        return {"ok": False, "available": False, "reason": "needs_snapshot_unavailable"}

    @router.get("/goal")
    def get_goal():
        if hasattr(brain, "get_companion_goal_snapshot"):
            return brain.get_companion_goal_snapshot()
        return {"ok": False, "available": False, "reason": "goal_snapshot_unavailable"}

    @router.get("/goal/auto")
    def get_goal_auto_execute_gate():
        if hasattr(brain, "get_companion_auto_execute_snapshot"):
            return brain.get_companion_auto_execute_snapshot()
        return {"ok": False, "available": False, "reason": "auto_execute_gate_unavailable"}

    @router.post("/goal/auto/tick")
    def tick_goal_auto_execute(payload: Dict[str, Any] | None = None, force: bool = False):
        if hasattr(brain, "tick_companion_auto_execute"):
            return brain.tick_companion_auto_execute(payload or {}, force=force)
        return {"ok": False, "available": False, "reason": "auto_execute_gate_unavailable"}

    @router.get("/goal/execution")
    def get_goal_execution():
        if hasattr(brain, "get_companion_goal_execution_snapshot"):
            return brain.get_companion_goal_execution_snapshot()
        return {"ok": False, "available": False, "reason": "goal_executor_unavailable"}

    @router.post("/goal/execute")
    def execute_goal(payload: Dict[str, Any] | None = None):
        if hasattr(brain, "execute_companion_goal"):
            return brain.execute_companion_goal(payload or {})
        return {"ok": False, "available": False, "reason": "goal_executor_unavailable"}

    @router.post("/goal/simulate")
    def simulate_goal(payload: Dict[str, Any]):
        if not hasattr(brain, "goal_selector"):
            return {"ok": False, "available": False, "reason": "goal_selector_unavailable"}
        return brain.goal_selector.select(payload or {})

    @router.get("/living-needs")
    def get_living_needs():
        if hasattr(brain, "get_living_needs_snapshot"):
            return brain.get_living_needs_snapshot()
        return {"ok": False, "available": False, "reason": "living_needs_unavailable"}

    @router.post("/living-needs/tick")
    def tick_living_needs():
        if hasattr(brain, "tick_living_needs"):
            return brain.tick_living_needs()
        return {"ok": False, "available": False, "reason": "living_needs_unavailable"}

    @router.post("/scenario/replay")
    def run_scenario_replay(payload: Dict[str, Any] | None = None):
        if hasattr(brain, "run_companion_e2e_scenario"):
            return brain.run_companion_e2e_scenario(payload or {})
        return {"ok": False, "available": False, "reason": "scenario_replay_unavailable"}

    @router.post("/scenario/e2e")
    def run_scenario_e2e(payload: Dict[str, Any] | None = None):
        if hasattr(brain, "run_companion_e2e_scenario"):
            return brain.run_companion_e2e_scenario(payload or {})
        return {"ok": False, "available": False, "reason": "scenario_replay_unavailable"}
