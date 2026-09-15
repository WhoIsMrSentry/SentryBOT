# Runtime / Behavioral-Quality Audit Report (post–Batch 6b)

**Status:** Complete — audit only; **no implementation authorized or performed**  
**Charter:** `RUNTIME_BEHAVIOR_AUDIT_CHARTER.md`  
**Substrate:** Batches 1–6b (closed single-foreground life-loop)  
**Invariant:** Locked throughout — one foreground goal; competition at formation only  
**Evidence date:** 2026-09-15  

---

## Executive verdict

| Question | Answer |
|----------|--------|
| Does the closed loop produce context-sensitive behavior? | **Yes, when context changes materially** (need, owner, hazards, novelty). |
| Does it merely cycle deterministically? | **Not as intent thrashing.** Stable context → fingerprint reuse (~95%). Mild score jitter often → **DEFER**, not a rotating carousel of intents. |
| Is a new abstraction / Batch 7 required? | **No.** No reproducible deficiency that the existing substrate cannot address was proven. |
| What remains? | **Watch-list** behavioral-quality notes (template HOW rigidity, session-local learning, agentic parallel path, fixed env RNG seed) — not greenlit work. |

**Implementation rule respected:** no new abstraction proposed.

---

## Method

1. Code/mechanism probe of formation, evaluator, life-loop, proactive, templates, config constants.  
2. Multi-tick formation + dry-run life-loop probe (`_audit_runtime_behavior_probe.py`, disposable evidence script).  
3. Hypotheses treated as **tests**, not assumptions.

---

## Hypothesis results

### H1 — Intention/context changes over time

**Verdict: SUPPORTED (with intentional damping) — severity: ok / watch**

| Experiment | Result |
|------------|--------|
| 20 ticks, **identical** context | `inspect_environment` ×20; **reuse_rate 0.95** |
| 24 ticks, **changing** need/owner/hazards/novelty | **7 unique** disposition/intent labels including `social_check_in`, `pause_and_observe`, `settle_or_rest`, `scan_for_company_then_rest`, `inspect_environment`; reuse_rate **0.0** |

**Interpretation:** Unchanged context correctly freezes intention (fingerprint). Material context shifts produce different intentions. Finite allowlist (~10 intents / 12 template keys) caps vocabulary but is not “stuck cycling A→B→A” under static input.

**Watch:** Mild need oscillation without clear dominant signal often yields **DEFER** (`weak_idle_below_activation`) rather than rich intention variety — conservative, not thrashing.

---

### H2 — Outcome accumulation → meaningful adaptation

**Verdict: SUPPORTED within session — severity: watch**

| Experiment | Result |
|------------|--------|
| Prefer A (`inspect_environment`) over B | before = A |
| 3× A failure | after = B (`look_around_and_learn`) |
| 4× A success after fails | still B; outcome_adj(A) = **−0.4** (cap math: failures outweigh successes) |
| Failures older than `outcome_window_s` | adj = **0.0** |

**Mechanisms:** intent-keyed evaluator deque (maxlen 24, window 900s), companion outcome → formation, selector need nudges.

**Watch:** Adaptation is **real but shallow and session-local** (no reboot persistence). Success does not quickly erase accumulated failure penalties within the window (by design of caps). Not a substrate gap requiring a new learning architecture.

---

### H3 — Proactive initiation useful vs repetitive / second brain

**Verdict: PARTIAL — severity: watch (not a single-goal gap)**

| Path | Role | GoalStore? |
|------|------|------------|
| Formation + life-loop | Embodied single foreground | Yes |
| Rituals / ProactivePlanner | Speech/expression; long cooldowns (e.g. idle≥~50s, max ~4/hr) | No |
| Agentic boredom → `agent.step` | Parallel actuation path | No shared lock with GoalStore |

**Interpretation:** Proactive speech is cooldown-gated (useful vs spam). Structural **watch** remains the **agentic parallel path**, not missing multi-goal. Existing formation + gates address companion embodiment; coordination policy would be the smallest future intervention *if* product evidence shows conflict — not authorized here.

---

### H4 — Completion → next intention

**Verdict: SUPPORTED — severity: ok**

Probe: dry-run execute → GoalStore status `completed` → next form with social context → `select social_check_in`, `active_or_waiting() is None`.

Matches Batch 6b scenario `test_life_loop_completion_clears_foreground_for_next_goal`. Hand-off is **next think tick**, not in-callback re-form (by design).

---

### H5 — Stale-goal / formation churn

**Verdict: SUPPORTED (anti-churn holds) — severity: ok / watch**

| Mechanism | Effect |
|-----------|--------|
| Fingerprint reuse | 95% reuse under static context |
| Resume before new need | GoalStore ACTIVE/WAITING owns execution |
| Resume cooldown bypass | Multi-tick progress without 8s stall |
| Soft interrupt / safety supersede | Legitimate replacement, not churn |
| Mild score drift life-loop (15 ticks) | Mostly DEFER; **2** executes; **2** unique goal ids; no active leftover |

**Watch:** `environment_policy` can still mutate overlays each select even when formation is reused (policy-layer garnish, not GoalStore churn). Resume plan vs `state["companion_goal"]` can diverge during WAITING — display/consistency watch only.

---

### H6 — Plan diversity in normal operation

**Verdict: WHAT varies; HOW is template-bound — severity: watch**

| Layer | Evidence |
|-------|----------|
| WHAT | Context-sensitive intents (H1 changing) |
| HOW | `INTENT_TO_TEMPLATE` **12** keys → fixed step templates via `build_for_intent` |
| Mid-run diversity | `ContextualReplanner` on **failure/blocked** only (`max_replans: 2`) |
| Stochastic garnish | `environment_policy` p=**0.18**, band 0.12, **seed 2701** (reproducible, not free-running entropy) |

**Interpretation:** Normal successful runs look repetitive at the **step** level by design. That is **not** proven insufficient without product telemetry showing “same template feels broken.” No plan-variant framework justified.

---

### H7 — Reboot continuity

**Verdict: PRODUCT QUESTION ONLY — severity: gap (gated)**

`goal_persistence.backend: memory`. GoalStore, evaluator outcomes, `companion_outcome` die with the process. World/relationship memory does not restore foreground goals.

**Do not implement** unless product requires cross-reboot session resume. Not an autonomy-architecture maturity milestone.

---

## Cross-cutting picture

```text
Stable context     → fingerprint reuse (anti-churn)     ✓ intended
Material context   → intention / disposition change     ✓ evidenced
Outcomes           → ranking shift within session         ✓ evidenced
Completion         → empty foreground → new form          ✓ evidenced
Successful HOW     → same templates until failure         ⚠ watch
Agentic boredom    → second actuation path                ⚠ watch
Reboot             → no foreground restore                ◌ product-only
```

Primary “looks deterministic” risk is **not** formation thrashing; it is **stable needs → same intent → same template steps** until needs/perception/outcomes/repetition thresholds move. That is coherent companion behavior, not a missing scheduler.

---

## Explicit non-recommendations

Do **not** start:

- Batch 7 / multi-goal / queues / workers / concurrent executors  
- Plan-variant frameworks / live LLM planning / RL / vector habit memory  
- SQLite GoalStore “because maturity”  
- Softening fingerprint or activation thresholds without product complaints of “too idle”

---

## If a future greenlight is ever warranted

Only after **product/runtime telemetry** shows a named, reproducible deficiency. Smallest-first candidates (not approved):

| If evidence shows… | Smallest existing-mechanism lever |
|--------------------|-----------------------------------|
| Agentic fights companion actuation | Policy/mutex — not a goal queue |
| Cross-reboot must resume foreground | Memory/backend seed for GoalStore + outcomes |
| Same template feels lifeless on success path | Narrow template alt or contextual replan trigger — only with scenario proof |

None of these are opened by this audit.

---

## Stable autonomy baseline

This audit closes the autonomy batch sequence for now. Batches **1–6b** are the **stable autonomy baseline**.

> Context-sensitive with deliberate stability, single-foreground, outcome-aware in-session, and capable of autonomous multi-tick progression.

Deterministic cycling is **not** a current problem. Do not add planning/scheduling layers without a demonstrated behavioral gap.

Future implementation only when runtime evidence shows measurable regression or unmet product behavior — not because another numbered batch feels inevitable.

