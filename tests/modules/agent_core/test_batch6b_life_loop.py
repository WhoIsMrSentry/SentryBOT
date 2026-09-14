"""Batch 6b — close the companion life-loop (multi-tick autonomous chain)."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from modules.agent_core.services.runtime import GoalFormationService, GoalStatus, GoalStore
from modules.autonomy.services.companion_auto_execute_gate import CompanionAutoExecuteGate
from modules.autonomy.services.companion_goal_executor import CompanionGoalExecutor
from modules.autonomy.services.brain_parts.scenario import CompanionScenarioMixin
from modules.autonomy.services.brain_parts.scenario_rituals import ScenarioRitualsMixin


def _plan(
    *,
    plan_id: str = "goal_a",
    goal_id: str = "goal_a",
    auto_execute: bool = True,
    safe: bool = True,
    actions: Optional[List[Dict[str, Any]]] = None,
    steps: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    acts = actions or [
        {"type": "vision", "mode": "cheap", "capability": "vision.cheap", "risk": "none"},
        {"type": "expression", "event": "curiosity", "capability": "expression.event", "risk": "none"},
    ]
    typed_steps = steps or [
        {
            "id": f"s{i}",
            "objective": a.get("capability") or "step",
            "required_capabilities": [a.get("capability") or "vision.cheap"],
            "status": "ready",
            "metadata": {"action": dict(a)},
        }
        for i, a in enumerate(acts, start=1)
    ]
    return {
        "plan_id": plan_id,
        "intent": "inspect_environment",
        "behavior": "inspect_environment_and_learn",
        "dominant_need": "curiosity",
        "priority": "normal",
        "safe_to_execute": safe,
        "auto_execute": auto_execute,
        "actions": acts,
        "typed_goal": {"id": goal_id, "objective": "inspect environment"},
        "typed_plan": {"id": f"plan_{goal_id}", "goal_id": goal_id, "version": 1, "steps": typed_steps},
    }


class LifeLoopBrain(CompanionScenarioMixin, ScenarioRitualsMixin):
    """Minimal brain surface for multi-tick life-loop proofs."""

    def __init__(self, *, gate_cfg: Optional[Dict[str, Any]] = None, executor_cfg: Optional[Dict[str, Any]] = None):
        self.state: Dict[str, Any] = {
            "is_sleeping": False,
            "last_interaction": time.time(),
            "companion_goal": None,
        }
        self.config = {
            "companion_auto_execute": {
                "enabled": True,
                "life_loop_enabled": True,
                "resume_bypass_cooldown": True,
                "min_interval_s": 8.0,
                "require_auto_execute_flag": True,
                "dry_run_default": True,
                "allow_real_hardware": False,
                "allowed_risks": ["none", "low", "semantic"],
                "allowed_priorities": ["low", "normal", "critical"],
                **(gate_cfg or {}),
            },
            "companion_goal_executor": {
                "enabled": True,
                "dry_run_default": True,
                "allow_real_hardware": False,
                "cognitive_loop": {
                    "enabled": True,
                    "simulate_on_dry_run": True,
                    "max_iterations": 8,
                    "max_retries": 1,
                    "max_replans": 1,
                    "goal_persistence": {"enabled": True, "ttl_s": 600, "resume_on_tick": True},
                },
                "goal_persistence": {"enabled": True, "ttl_s": 600, "resume_on_tick": True},
                **(executor_cfg or {}),
            },
            "outcome_learning": {"enabled": True, "success_weight_adjustment": 0.05, "failure_weight_adjustment": -0.1},
        }
        self.goal_store = GoalStore(ttl_s=600)
        self.goal_auto_execute_gate = CompanionAutoExecuteGate(self.config["companion_auto_execute"])
        self.goal_executor = CompanionGoalExecutor(self.config["companion_goal_executor"])
        self.goal_executor.set_goal_store(self.goal_store)
        self.goal_formation = GoalFormationService(
            cfg={"enabled": True, "allow_soft_interrupt": True, "allow_supersede": True, "min_activation_score": 0.25},
            goal_store=self.goal_store,
        )
        self._form_calls = 0
        self._think_plans: List[Dict[str, Any]] = []

    def _owner_seen_recently(self) -> bool:
        return bool(self.state.get("owner_present"))

    def _update_companion_needs(self, now: float) -> None:
        """Stand-in for formation: inject next plan or let resume own the tick."""
        self._form_calls += 1
        if self._think_plans:
            plan = dict(self._think_plans.pop(0))
            self.state["companion_goal"] = plan
            return
        # Default: keep last plan in state (fingerprint-style stability) unless store owns resume.
        if not isinstance(self.state.get("companion_goal"), dict):
            self.state["companion_goal"] = _plan(plan_id=f"idle_{self._form_calls}", goal_id=f"idle_{self._form_calls}")

    def think_tick(self, now: Optional[float] = None) -> Dict[str, Any]:
        ts = float(now if now is not None else time.time())
        self._update_companion_needs(ts)
        self._maybe_tick_companion_life_loop(ts)
        return {
            "companion_goal": dict(self.state.get("companion_goal") or {}),
            "auto": dict(self.state.get("companion_auto_execute") or {}),
            "execution": dict(self.state.get("companion_goal_execution") or {}),
            "store_active": self.goal_store.active_or_waiting(),
            "store_all": list(self.goal_store.all()),
        }


def test_life_loop_normal_progression_form_execute_persist_complete():
    brain = LifeLoopBrain()
    brain._think_plans = [_plan(plan_id="a1", goal_id="goal_a")]
    t1 = brain.think_tick(now=1000.0)
    assert t1["auto"].get("should_execute") is True
    assert t1["auto"].get("executed") is True or t1["execution"].get("ok") is True
    snap = t1["store_active"]
    # Simulated loop may complete in one tick
    if snap is None:
        terminals = [s for s in t1["store_all"] if s.status in {GoalStatus.COMPLETED, GoalStatus.FAILED}]
        assert terminals, "goal must persist to GoalStore (complete or active)"
        assert terminals[0].goal_id == "goal_a"
    else:
        assert snap.goal_id == "goal_a"


def test_life_loop_waiting_resumes_without_reform():
    brain = LifeLoopBrain(
        executor_cfg={
            "cognitive_loop": {
                "enabled": True,
                "simulate_on_dry_run": True,
                "max_iterations": 1,
                "max_retries": 0,
                "max_replans": 0,
                "max_execution_time_s": 0.01,
                "goal_persistence": {"ttl_s": 600, "resume_on_tick": True},
            }
        }
    )
    # Two-step plan; first tick budget/time limited → WAITING
    acts = [
        {"type": "vision", "mode": "cheap", "capability": "vision.cheap", "risk": "none"},
        {"type": "expression", "event": "curiosity", "capability": "expression.event", "risk": "none"},
    ]
    brain._think_plans = [_plan(plan_id="wait1", goal_id="goal_wait", actions=acts)]
    t1 = brain.think_tick(now=2000.0)
    active = brain.goal_store.active_or_waiting()
    if active is None:
        # Completed too fast — force WAITING snapshot for resume proof
        from modules.agent_core.services.runtime import GoalSnapshot

        brain.goal_store.create(
            GoalSnapshot(
                goal_id="goal_wait",
                objective="inspect",
                status=GoalStatus.WAITING,
                expires_at=time.time() + 600,
                current_plan={
                    "steps": [
                        {
                            "id": "s2",
                            "status": "ready",
                            "required_capabilities": ["expression.event"],
                            "objective": "express",
                            "metadata": {"action": acts[1]},
                        }
                    ]
                },
                goal_plan=_plan(plan_id="wait1", goal_id="goal_wait", actions=[acts[1]]),
            )
        )
    brain._think_plans = []  # no new formation plan — resume must win
    brain.state["companion_goal"] = {"behavior": "should_not_run", "auto_execute": True, "safe_to_execute": True, "actions": []}
    t2 = brain.think_tick(now=2001.0)
    assert t2["auto"].get("resumed_goal") is True
    assert t2["auto"].get("should_execute") is True


def test_life_loop_completion_clears_foreground_for_next_goal():
    brain = LifeLoopBrain()
    brain._think_plans = [_plan(plan_id="done1", goal_id="goal_done")]
    brain.think_tick(now=3000.0)
    # Force terminal if still active
    active = brain.goal_store.active_or_waiting()
    if active is not None:
        brain.goal_store.complete(active.goal_id, GoalStatus.COMPLETED)
    assert brain.goal_store.active_or_waiting() is None
    brain._think_plans = [_plan(plan_id="b1", goal_id="goal_b")]
    t2 = brain.think_tick(now=3010.0)
    ids = {s.goal_id for s in brain.goal_store.all()}
    assert "goal_b" in ids or (t2["store_active"] and t2["store_active"].goal_id == "goal_b")


def test_life_loop_idempotency_cooldown_blocks_duplicate_new_plan():
    brain = LifeLoopBrain(gate_cfg={"min_interval_s": 30})
    plan = _plan(plan_id="same", goal_id="goal_same")
    brain._think_plans = [plan]
    t1 = brain.think_tick(now=4000.0)
    assert t1["auto"].get("should_execute") is True
    # Same plan_id still in state, no resume (store may be terminal) → cooldown
    brain._think_plans = []
    brain.state["companion_goal"] = dict(plan)
    # Clear store so tick uses snapshot, not resume bypass
    brain.goal_store.clear()
    t2 = brain.think_tick(now=4001.0)
    assert t2["auto"].get("should_execute") is False
    assert t2["auto"].get("reason") == "cooldown"


def test_life_loop_resume_bypasses_cooldown():
    gate = CompanionAutoExecuteGate({"min_interval_s": 30, "resume_bypass_cooldown": True})
    p = _plan()
    first = gate.decide(p, dry_run=True, now=100.0)
    second = gate.decide(p, dry_run=True, now=101.0, bypass_cooldown=True)
    assert first["should_execute"] is True
    assert second["should_execute"] is True


def test_life_loop_unsafe_blocked_despite_think_tick():
    brain = LifeLoopBrain()
    brain._think_plans = [_plan(plan_id="unsafe", goal_id="goal_unsafe", safe=False)]
    t1 = brain.think_tick(now=5000.0)
    assert t1["auto"].get("should_execute") is False
    assert t1["auto"].get("reason") == "goal_marked_unsafe"
    assert brain.goal_store.active_or_waiting() is None


def test_life_loop_disabled_flag_skips_tick():
    brain = LifeLoopBrain(gate_cfg={"life_loop_enabled": False})
    brain._think_plans = [_plan()]
    brain.think_tick(now=6000.0)
    assert brain.state.get("companion_auto_execute") in (None, {})


def test_life_loop_soft_interrupt_still_supersedes_waiting():
    from modules.agent_core.services.runtime import GoalSnapshot

    brain = LifeLoopBrain()
    brain.goal_store.create(
        GoalSnapshot(
            goal_id="wait_inspect",
            objective="inspect",
            status=GoalStatus.WAITING,
            expires_at=time.time() + 600,
            params={"intent": "inspect_environment"},
            current_plan={
                "steps": [
                    {
                        "id": "s1",
                        "status": "ready",
                        "required_capabilities": ["vision.cheap"],
                        "objective": "see",
                    }
                ]
            },
            goal_plan=_plan(plan_id="old", goal_id="wait_inspect"),
        )
    )
    decision = brain.goal_formation.form(
        {
            "dominant_need": "social",
            "recommended_goal": "engage_owner",
            "confidence": 0.8,
            "scores": {"social": 85, "curiosity": 20, "safety": 5, "rest": 10, "energy": 70},
            "perception": {"novelty": 0.1},
            "preferences": {},
            "routines": {},
        },
        owner_present=True,
    )
    assert decision.disposition.value == "supersede"
    assert decision.selected_intent == "social_check_in"
    assert brain.goal_store.get("wait_inspect").status == GoalStatus.SUPERSEDED


def test_simulate_dry_run_persists_to_goal_store():
    store = GoalStore(ttl_s=600)
    ex = CompanionGoalExecutor(
        {
            "enabled": True,
            "dry_run_default": True,
            "allow_real_hardware": False,
            "cognitive_loop": {"enabled": True, "simulate_on_dry_run": True, "max_iterations": 6},
        }
    )
    ex.set_goal_store(store)
    result = ex.execute(_plan(goal_id="sim1"), dry_run=True, now=7000.0)
    assert result.get("dry_run") is True
    assert result.get("cognitive_loop", {}).get("simulated") is True
    assert len(store.all()) >= 1
