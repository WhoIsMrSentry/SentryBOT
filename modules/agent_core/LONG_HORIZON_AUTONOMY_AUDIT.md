# Long-Horizon Autonomy Design Audit (post–Batch 6a)

**Status:** Audit complete — design only; no implementation in this pass  
**Follow-up:** Think→execute gap closed by **Batch 6b** (`BATCH6B_COMPLETION.md`); multi-goal still rejected.  
**Substrate:** Batches 1–6a (stable); 6b closes life-loop only  
**Multi-goal assumption:** Rejected unless evidence forces it  
**Primary question:** Does SentryBOT behave autonomously over many ticks, or only make better one-tick decisions?

---

## Verdict

| Question | Answer |
|----------|--------|
| Is multi-goal / Batch 6b required? | **No.** Evidence does not expose concurrent-intention insufficiency. |
| Is “no Batch 6b implementation” correct? | **Yes.** |
| Are long-horizon mechanisms already sufficient end-to-end? | **Partially.** In-process governance is strong; the life-loop **think → execute** path is not closed. |
| What would a narrow next batch be (if any)? | Close the companion **formation → auto-execute** loop inside `_think`, and optionally harden session continuity — **not** a goal queue. |

---

## Design lock (unchanged)

> SentryBOT uses a single-foreground-goal autonomy model by design.  
> New goals compete during formation; they do not coexist as independently executing goals.

---

## Audit dimensions

### 1. Long-horizon continuity — intention across many ticks

**In-process: sufficient.**  
`GoalStore.active_or_waiting()` + formation `RESUME` + fingerprint reuse + WAITING/ACTIVE persist + soft interrupt / safety supersede give coherent single-intent continuity within a process (TTL default 600s, non-sliding `expires_at` on updates).

**Life-loop closed loop: gap.**  
Formation runs every think tick (`_update_companion_needs` → `goal_selector.select`).  
`tick_companion_auto_execute` (resume + execute) is **not** called from `AutonomyBrain._think()` — only via `POST /autonomy/goal/auto/tick` and TUI dry-run.  
So the system can **decide** repeatedly without **advancing** the foreground goal unless something external ticks auto-execute.

| Continuity breaker | Mechanism |
|--------------------|-----------|
| Expire | `expires_at` → `EXPIRED` |
| Terminal | `complete()` + prune |
| Sticky REPLANNING | healed → FAILED / WAITING |
| Soft interrupt | WAITING low-urgency → SUPERSEDED |
| Safety supersede | pause_and_observe |
| Repetition suppress | same intent ≥2 in window |
| No work left | `active_or_waiting()` → None |

**Multi-tick tests exist** (Batch 4/5/6a resume, soft interrupt, outcomes) but **not** a full brain `_loop` think→execute→think e2e.

---

### 2. Outcome accumulation — stable preferences vs local penalties

**Session: sufficient (bounded).**  
Intent-keyed `GoalEvaluator.outcomes` (deque maxlen 24, window ~900s) with failure/success score adjustments; companion `_record_companion_outcome` feeds evaluator + `brain.state["companion_outcome"]`; selector may nudge need scores / avoid tags.

**Long-term / reboot: gap (optional product).**  
No disk seed of outcomes; restart clears evaluator + `companion_outcome`. Preferences are **local session memory**, not durable habits. That is enough for companion-scale autonomy if product does not require reboot continuity.

Does **not** justify multi-goal — justifies optional persistence of the **same** single-goal learning state if required.

---

### 3. Proactive behavior — initiate without becoming a second brain

**Formation without speech: sufficient.**  
Needs tick + `GoalFormationService` produce a companion plan on think ticks.

**Proactive speech paths:** rituals / `proactive_planner` — speech/expression only, not competing GoalStore executors.

**Coordination gap (optional):** agentic boredom path (`_make_agentic_decision` → `agent.step` / BehaviorComposer) can act in parallel with the companion pipeline; no shared foreground lock with GoalStore. Risk is **two actuation brains**, not missing goal concurrency. Fix (if needed): policy/mutex, not a queue.

---

### 4. Goal completion → next intention

**Sufficient (next think tick).**  
Terminal statuses → `goal_store.complete()` → excluded from `active_or_waiting()` → next formation sees empty foreground and ranks anew; outcome available for ranking on the next needs update. No immediate re-form inside the execution callback (by design — one formation per think tick).

---

### 5. Cross-reboot continuity

**Gap — only if product requires it.**  
`goal_persistence.backend: memory`. GoalStore, evaluator deques, and `companion_outcome` are process-local. World/relationship memory elsewhere does **not** restore foreground goal snapshots.  
**Do not** build reboot persistence “because maturity”; only if a real product requirement appears.

---

### 6. Plan diversity under normal conditions

**Mid-execution: sufficient.**  
`ContextualReplanner` + `PlanPolicyGate` diversify on failure/blocked context (rules-first; LLM assist off by default; `max_replans: 2`).

**Formation-time HOW: rigid by design.**  
`build_for_intent` → template map. Diversity of **what** comes from formation; diversity of **how** is recovery/replan, not a variant framework. Batch 6a correctly deferred speculative plan variants — this audit finds **no new evidence** that a variant framework is required.

---

## Summary matrix

| Dimension | Severity | Multi-goal needed? |
|-----------|----------|-------------------|
| In-process intention continuity | Sufficient | No |
| Think ↔ execute closed loop | **Gap** | No — wire tick, don’t queue |
| Session outcome learning | Sufficient | No |
| Durable / reboot preferences | Gap (optional) | No |
| Proactive formation | Sufficient | No |
| Agentic vs companion actuation | Gap (optional coordination) | No |
| Completion → next | Sufficient | No |
| Mid-run plan diversity | Sufficient | No |
| Formation plan-variant framework | Not justified | No |

---

## What this audit rejects

- Batch 6b = multi-goal arbitration / priority scheduler / background goal workers  
- Speculative plan-variant frameworks without scenario failure of templates+replan  
- Treating missing reboot persistence as an autonomy maturity milestone by default  

## What a narrow follow-up *could* be (only after greenlight)

**Batch 7a candidate (if desired):** “Close the companion life-loop” — call gated `tick_companion_auto_execute` from `_think` after needs/formation, with dry-run/safety gates unchanged; add multi-tick life-loop scenario tests proving intention advances across ticks.

Optional later (product-gated): memory backend for GoalStore + outcome seed; agentic/companion actuation policy.

---

## Evidence anchors

- `modules/autonomy/services/brain_parts/decision.py` — `_think` forms needs; does not auto-execute  
- `modules/autonomy/services/brain_parts/scenario_rituals.py` — `tick_companion_auto_execute` + resume  
- `modules/autonomy/api/companion_routes.py` — HTTP tick only  
- `modules/agent_core/services/runtime/goal_store.py` — single foreground + lifecycle  
- `modules/agent_core/services/runtime/goal_evaluator.py` — outcomes + soft interrupt  
- `modules/agent_core/architecture_agent_core.md` — design lock  
- Tests: `test_batch4_*`, `test_batch5_*`, `test_batch6a_*` (unit/scenario; not full brain loop e2e)
