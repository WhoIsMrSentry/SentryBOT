# Batch 6b Completion Report — Close the Companion Life-Loop

**Status:** Complete  
**Scope:** Wire gated auto-execution into `_think()` for the existing single foreground goal  
**Not in scope:** Multi-goal queues, workers, schedulers, SQLite, plan variants, RL

## Transition

```text
Before:
_think() → form/resume → may stall → external tick_companion_auto_execute()

After:
_think()
  → form/resume (_update_companion_needs)
  → CompanionAutoExecuteGate (_maybe_tick_companion_life_loop)
  → CompanionGoalExecutor → CompanionExecutionLoop
  → GoalStore
       ↺ next _think()
```

## Delivered

1. **Life-loop tick** — `decision._think` calls `_maybe_tick_companion_life_loop` after needs/formation (`life_loop_enabled`, default true).
2. **Same stack** — reuses `tick_companion_auto_execute` → gate → executor → loop; no second execution path.
3. **Resume cooldown bypass** — `bypass_cooldown` when GoalStore resumes ACTIVE/WAITING so multi-tick progress is not stalled by `min_interval_s`.
4. **Dry-run GoalStore simulation** — `simulate_on_dry_run` runs the cognitive loop with simulated capabilities when a GoalStore is present (PC-safe progression).
5. **Guards preserved** — unsafe / auto_execute flag / risk / deferred / soft interrupt / safety supersede unchanged.

## Evidence

- `tests/modules/agent_core/test_batch6b_life_loop.py`
- Regression: **415** agent_core + autonomy tests passed

## Invariant

Exactly one foreground goal; competition at formation; execution governed by the existing safety and policy stack.

## Posture after 6b

No automatic next implementation batch. No Batch 6b follow-on and no presumed Batch 7.

**Next greenlight:** runtime/behavioral-quality audit only — see `RUNTIME_BEHAVIOR_AUDIT_CHARTER.md`. Implement only if that audit proves a narrow gap the existing mechanisms cannot address.
