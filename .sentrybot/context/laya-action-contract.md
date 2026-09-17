# Laya Action Proposal Contract

**Status:** Fail-closed proposal builder is implemented; proposal generation is config-disabled by default and direct Laya dispatch stays disabled until each applicable item below has real-model verification, implementation, and regression coverage.

## Current boundary

`LayaEngine` currently classifies `target_module`, `is_direct_command`, affect and urgency. `LayaDecision.suggested_action` exists as a field but `decide()` does not populate it. A target such as `arduino_serial` does not identify an actuator, an operation, or safe arguments. `emergency_stop -> stop_follow` is not equivalent to stopping the motors.

The installed Laya 0.3.5 runtime source (`.venv/Lib/site-packages/laya/agent.py`) accepts `choice`, `score`, and `noul` question types in `system_one()` and returns typed answers with confidence/probabilities; it does not provide a free-form JSON/action-argument output type. Therefore any future proposal must be assembled from multiple bounded choice answers (for example, a finite light color/effect) and each required field must independently meet its configured confidence threshold. Continuous actuator values must not be guessed from these classifications.

The code now contains a pure `set_lights` proposal builder in `modules/agent_core/services/laya_action_contract.py`. It accepts only direct `neopixel` decisions, requires confidence thresholds for the module, direct-command, color, and effect answers, rejects unknown choices/non-finite confidence values, checks the configured action allowlist, and returns data only. `config/agent.yaml` keeps `action_proposals.enabled: false`; no dispatch call is wired from this proposal.

## Real-model confidence finding

CPU inference succeeded under the existing Python 3.11 environment after running the approved interpreter directly. With the production Laya questions, sampled Turkish inputs produced:

| Input | Target / confidence | Direct / confidence | Urgency / confidence | Emergency result after gate |
|---|---|---|---|---|
| `Işıkları kapat` | `emergency_stop` / 0.8273 | direct / 0.8297 | 2.059 / 0.5410 | Rejected |
| `Sentry hakkında ne düşünüyorsun?` | `speak` / 0.5004 | conversation / 0.5971 | 2.4434 / 0.2844 | Rejected |
| `Motorları acil durdur, çarpacaksın!` | `emergency_stop` / 0.9340 | direct / 0.9818 | 2.2406 / 0.1849 | Accepted by confident emergency target |
| `Dur hemen!` | `emergency_stop` / 0.9503 | direct / 0.9696 | 2.0872 / 0.1601 | Accepted by confident emergency target |

This exposed a real false-positive in the old emergency predicate: it accepted any `emergency_stop` target or urgency score over threshold regardless of confidence/directness. Emergency now requires a direct command plus either a high-confidence emergency target or a high-confidence emergency urgency score. Non-emergency high urgency also requires configured confidence before sensor/mood urgency effects. Thresholds are in `tri_layer.laya.urgency`; current defaults are target 0.90, direct 0.80, urgency 0.80, and ordinary high-urgency confidence 0.60. Tests pin the observed false-positive and positive emergency samples.

When the experimental finite action questions were added to the same model call, `Işıkları mavi yap` returned color `pink` at 0.2894 confidence and effect `unspecified` at 0.3754; the action proposal is correctly rejected. This is not ready for actuator dispatch; action extraction needs further model/question calibration and real prompt-set evaluation.

The repeatable offline evaluator is `tools/evaluate_laya_action_proposals.py`. Its fixed 14-example Turkish sample currently reports target top-choice accuracy 0.643; at the 0.60 confidence gate, target coverage 0.571 and accepted-target accuracy 0.625. Direct-command top-choice accuracy is 0.929; confidence-gated direct coverage 0.357 and accepted-direct accuracy 1.0. Current explicit-color top-choice accuracy is **0.125 (1/8)** with zero explicit colors accepted at 0.85 confidence. Two alternative explicit color instructions each reached 1.0 top-choice accuracy and 0.875 explicit-color confidence coverage, but only 0.167/0.333 specificity across six no-color controls; each produced **2 high-confidence false colors**. Explicit effect accuracy is 0.667 (2/3), confidence-gated emergency accuracy 1.0 (14/14), and the current policy creates **0 proposals**. The color metric counts only prompts with an explicit requested color; chat/control cases cannot inflate it. This small fixed sample is a calibration check, not a general benchmark. Keep action proposals disabled until a larger held-out set demonstrates adequate precision and coverage.

A third experimental question combines color, `turn_off`, and `no_light_action` in one finite choice. On the same 14 examples, joint action accuracy was 0.500; explicit-color accuracy was 0.750 with only 0.375 coverage at confidence >=0.85 and 1.000 accuracy among accepted explicit colors. On the six no-color controls, specificity was 0.167, with **3 high-confidence false color/action answers**. The combined question therefore does not fix the false-positive issue and is not promoted to production. The sample is unchanged and these prompt variants are exploratory comparisons, not independent validation.

The evaluator was then expanded to 32 hand-labeled Turkish examples: 18 explicit color/off commands and 14 no-explicit-color controls, including color discussion, camera questions, and generic light commands. On this expanded calibration set, the conservative/current color question scored 0.111 explicit accuracy and 0.857 no-color specificity, with zero high-confidence false colors; the Turkish explicit variant scored 1.000 explicit accuracy with 0.778 confidence coverage but only 0.214 no-color specificity and 4 high-confidence false colors; the English/bilingual variant scored 0.944 explicit accuracy with 0.889 coverage, 0.286 specificity, and 5 high-confidence false colors. The joint action question scored 0.625 overall and 0.778 explicit-color accuracy, but only 0.222 explicit-color confidence coverage, 0.429 no-color specificity, and 4 high-confidence false positives. Emergency labels remained 32/32 and proposal count remained zero. This is still a prompt-calibration set, not an independent holdout. Results reinforce keeping proposals disabled.

An evaluator-only deterministic Turkish command parser was compared with the frozen Laya questions on a separate 30-example final holdout (14 explicit color/off commands, 16 controls; zero text overlap with calibration/parser-development lists). The parser scored 0.967 overall, 0.929 on explicit color/off, and 1.000 specificity on unspecified controls. On the same examples, the current model question scored 0.433 overall (0.143 explicit accuracy, 0.688 specificity, 1 high-confidence false positive); Turkish explicit scored 0.533 overall (1.000 explicit accuracy, 0.786 coverage, 0.125 specificity, 8 high-confidence false positives); English/bilingual scored 0.567 (1.000 explicit accuracy, 0.714 coverage, 0.188 specificity, 9 high-confidence false positives); joint scored 0.500 (0.786 explicit accuracy, 0.286 coverage, 0.250 specificity, 4 high-confidence false positives; accepted explicit accuracy 0.750). These are small hand-authored datasets and the parser has not been broadly validated. The parser remains isolated to the evaluator; it is not production code, proposal authority, or a dispatch path. Do not tune against the final holdout; any future parser changes need a new untouched test split.

A separate 30-example intent/safety holdout was added with five samples for each of the six target classes. On this split, target accuracy was 0.600; class accuracies were neopixel 0.400, arduino_serial 1.000, emergency_stop 0.800, speak 0.200, camera 1.000, and system2_chat 0.200. At the configured 0.60 confidence gate, target coverage was 0.700 and accepted-target accuracy 0.714. Direct-command accuracy was 0.900; confidence coverage 0.700 and accepted-direct accuracy 1.000. Confidence-gated emergency accuracy was 0.933 with zero false positives and 2 false negatives; high-urgency accuracy was 0.833 with zero false positives and 5 false negatives. Explicit effect top-choice accuracy was 0.500 (2/4), with zero answers meeting the 0.85 proposal threshold. No proposal or tool execution is part of this evaluator. The split is small and must remain untouched; it identifies target classification (especially speak/system2_chat), emergency recall, urgency recall, and effect confidence as remaining calibration gaps.

Two additional target/effect question variants were tested only on the 32-example development set. The longer Turkish target variant scored 0.188 accuracy and 0.174 accepted accuracy at 0.719 coverage. The concise English target variant scored 0.500 accuracy, but only 0.188 coverage and 0.667 accepted accuracy. An explicit-effect question reached 0.800 top-choice accuracy on five labeled effects, but 0.400 confidence coverage and only 0.500 accuracy among accepted answers. Neither target variant nor the effect variant is a viable proposal gate; none was run against the intent holdout. Production questions remain unchanged. This work produced evaluation evidence, not a completed rollout gate, so it does not increase the integration completion estimate.

A new balanced 30-example intent development split (five examples for each target) compared current, explicit Turkish, and explicit English target questions. Current target accuracy was 0.467, accepted accuracy 0.667 at 0.500 coverage; Turkish was 0.500 / 0.857 / 0.467; English was 0.600 / 0.786 / 0.467. Turkish had 2 emergency false negatives versus 3 for current; English also had 3. Direct accuracy was 0.933 with 1.000 accepted accuracy at 0.633 coverage. Urgency accuracy was 0.800 with 1 false positive and 5 false negatives. Effect variants each scored 0.500 across four examples; current coverage was 0.500, explicit-question coverage 0.250, with accepted accuracy 1.000 for both. The Turkish target candidate was selected on development results and tested once against the previously untouched 30-example intent holdout. It regressed target accuracy from 0.600 to 0.433, accepted accuracy from 0.714 to 0.647, and emergency accuracy from 0.933 to 0.900 (false negatives increased from 2 to 3). Candidate rejected; production remains unchanged. This holdout is now consumed for this comparison; future candidates require a new untouched test split.

A separate binary `explicit_audio_request` question was then added to the intent development evaluation to distinguish explicit spoken-output commands from ordinary dialogue. It scored 0.733 accuracy, but precision and recall were both 0.0 (3 false positives and all 5 explicit speak requests missed). Applying it only as a speak/system2_chat refiner at confidence gates 0.60, 0.80, or 0.90 left target accuracy unchanged at 0.467. This signal is rejected and must not be used in production.

Local model inference was attempted using the cached multilingual snapshot, but the current Python 3.12 runtime cannot import the venv's Torch binary (`torch_python.dll`, Windows error 126). A Python 3.12-compatible Torch wheel was then approved for an isolated `.laya_runtime` install; the 124.1 MB download stalled after 7.6 MB at roughly 73 kB/s and repeatedly lost its connection, so installation was stopped before any package was installed. The SDK interface is confirmed by source inspection, while real model behavior for additional action questions remains unverified until inference runs on a compatible environment.

Laya classification may select the short response path and provide diagnostic `laya_hint` telemetry. It must not call `ToolRegistry.execute()` from the classifier or turn a `suggested_tool` string into authority.

## Proposal shape

When the model/runtime can provide action arguments, they must be represented as a typed proposal before dispatch:

```json
{
  "schema_version": 1,
  "action": "<registered, explicitly approved tool name>",
  "arguments": {},
  "confidence": 0.0
}
```

The runtime must bind this proposal to the current user turn and its request id. It must not accept caller-supplied `source`, `priority`, `ttl_ms`, hardware payloads, URLs, or arbitrary tool names from Laya.

## Validation requirements

Reject the proposal without side effects when any of these conditions holds:

- It is missing, malformed, stale, for a different request, or has an unsupported schema version.
- `action` is not in a small explicit allowlist. Generic `queue_action`, arbitrary Arduino commands, `stop_follow`, and unrestricted motion are not implicitly allowlisted.
- The proposal is not a confident direct command, or the required module/direct confidence is below configured thresholds.
- Arguments are absent, contain unknown keys, have the wrong types, or exceed per-action limits. Do not silently coerce malformed model output into a valid actuator value.
- The action's existing safety/capability gate or resource arbiter rejects it.

Thresholds and per-action numeric bounds must come from configuration. Validators are fail-closed; inference or validation errors leave the normal Agent/Autonomy path available.

## Execution path

For an approved non-emergency action, dispatch only through the existing registered tool implementation so that its resource arbiter and downstream owner remain in force. The action must also pass the runtime owner's safety/capability policy; if a tool currently lacks that gate, it cannot be enabled for Laya dispatch until the gate is added and tested. Arduino payloads must use `modules/arduino_serial/contract.py` builders and validated request/ACK behavior.

Emergency stop is a separate reflex contract owned by Autonomy/SpinalCord. It must invoke a validated motor stop operation, never infer `stop_follow` as a substitute, and must not bypass the action/resource safety boundaries for unrelated actions.

## Rollout gates

1. Extend Laya output with a structured action proposal and prove the runtime/model actually returns it; classification-only output remains non-dispatchable.
2. Add an explicit allowlist with per-action typed schemas, config-driven thresholds/bounds, and a pure validator. Cover missing, extra, malformed, low-confidence, stale, and out-of-range cases.
3. Add a dispatcher that calls the existing tool registry and preserves tool/action/resource arbiters and autonomy capability checks. Assert invalid proposals produce zero calls.
4. Implement and test the emergency motor-stop operation through the authoritative spinal/Arduino contract path before treating emergency output as executable.
5. Run mock/integration tests, then perform model and hardware acceptance on the target device. Hardware acceptance must verify stop behavior, cancellation/cooldown, ACK/timeout behavior, and that arbitrary model output cannot actuate the robot.

Until all applicable gates pass, Laya remains a classifier/telemetry/affect signal only; ordinary LLM and Autonomy action pathways retain ownership.

## 2026-09-27 — literal audio-command parser experiment

An evaluator-only deterministic parser was measured on the already-used 30-example intent development split and scored 30/30 (5 explicit speech/sound commands found; no false positives). A new, disjoint 30-example audio set was then frozen and evaluated once: 8/8 explicit commands detected, with 4 false positives among 22 non-command controls; accuracy 0.867, precision 0.667, recall 1.000. The false positives came from questions/discussion containing command-like verbs. Because of those false positives, this parser is not suitable as an intent/dispatch gate. The split is now consumed and must not be used for tuning.

The parser and `--audio-parser-holdout-only` mode remain offline evaluator code. The mode does not load Laya/Torch, create proposals, or call tools/hardware. This experiment does not change production prompts, routing, or `action_proposals.enabled: false`; no rollout gate was closed.

## 2026-09-27 — request-bound proposal validation

Added pure helpers to bind an inert proposal to the current request ID and validate its exact schema, allowlisted `set_lights` name, exact typed argument keys/values, confidence threshold, and request ID. Wrong-request, malformed, extra-field, unsupported-schema, low-confidence, or unapproved proposals fail closed. Regression tests cover these cases. The validator is not wired to ToolRegistry or any dispatcher; it cannot execute an action, and the feature remains disabled. This closes only the pure validation substep; dispatcher, request lifecycle integration, independent intent quality, emergency stop, and hardware acceptance remain open.

The agent request path now generates a separate internal UUID per admitted turn and binds any inert Laya action proposal to it. `trace_id` remains observability metadata and is not treated as request authority because API callers can supply it. The UUID is cleared with the turn; the native-tool execution path still does not validate or dispatch Laya proposals.

## 2026-09-27 — tool-owner safety review

The current `set_lights` compatibility tool calls `queue_action("lights", ...)`; that reaches the agent-core `ActionArbiter` and its configured `ActionSafetyFilter`, then the registered lights handler claims the expression-light lease and calls the Autonomy client. The filter currently has no lights-specific capability approval, and this handler path does not call Autonomy's `CapabilityExecutor`. `ToolRegistry.execute()` has its separate tool-execution arbiter, but that alone is not the runtime owner's capability decision. Therefore no Laya dispatcher or execute-calling simulation seam was added: it would not prove the required owner-side safety gate. A safe dispatcher remains blocked on an explicit Autonomy-owned capability approval path for Laya-originated lights requests, with tests showing denial produces zero handler/hardware calls. Existing Laya feature configuration remains disabled.
