# Batch 6a Completion Report — Single-Goal Governance Refinement

**Status:** Complete  
**Scope:** Lifecycle hygiene, outcome→evaluator, soft interrupt  
**Out of scope:** Multi-goal queues, background workers, concurrent goals, speculative plan-variant frameworks

## Pipeline invariant (preserved)

```text
ONE foreground goal
        ↓
GoalFormation
        ↓
GoalPolicyGate
        ↓
build_for_intent
        ↓
PlanPolicyGate
        ↓
ExecutionLoop
        ↓
Observe → Evaluate → Recover/Replan
        ↺
```

## Delivered

### 1. Lifecycle hygiene
- `GoalStore.cancel(reason)` → meaningful `CANCELLED`
- `heal_stuck_replanning()` — no work → `FAILED`; with work → `WAITING`
- `prune_terminals()` — bounded keep + max age
- Execution persist maps sticky `REPLANNING` and calls `complete()` on terminals

### 2. Outcome → evaluator
- Intent-keyed `GoalEvaluator.record_outcome`
- Bounded failure penalty / success bonus in candidate scoring
- Scenario: **intent A failure → A less attractive than B** (proven in `test_outcome_failure_makes_intent_a_less_attractive_than_b`)
- Companion `_record_companion_outcome` feeds formation evaluator

### 3. Soft interrupt (single foreground)
- Owner present + high social can displace low-urgency `WAITING` explore/idle intents via `SUPERSEDE`
- Safety supersede unchanged
- Weak curiosity without owner still resumes
- Resume candidates are **excluded** from ranked_best under soft interrupt (not merely skipped for early return)

### 4. Plan variants
- Deferred — no test demanded a variant framework

## Evidence
- `tests/modules/agent_core/test_batch6a_single_goal_governance.py`
- Regression: Batch 4/5/6a + companion execution loop green

## Design lock
Batch 6 remains **single-goal by design**. No multi-goal abstraction was introduced for 6a.

> **SentryBOT uses a single-foreground-goal autonomy model by design.**
> New goals compete during formation; they do not coexist as independently executing goals.

Do not start multi-goal arbitration without long-horizon audit evidence. Next question: longer-horizon autonomy vs better one-tick decisions (continuity, outcome accumulation, proactive initiation, completion semantics, optional reboot continuity, plan diversity).
