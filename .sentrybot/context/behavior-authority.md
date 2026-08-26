# Behavior Authority

SentryBOT has two brains in one process. They are not peers.

| Role | Owner | Does | Does not |
|---|---|---|---|
| Plan / decide | `autonomy` (`AutonomyBrain`) | Sense-think-act loop, needs, companion goals, owner-guard, when to speak or move | Direct LED/OLED/ear writes; skipping the hardware gate |
| Orchestrate a turn | `agent_core` (`AgentOrchestrator`) | LLM tool-calling, tri-layer, speech chunks, action/vision/expression *leases* | Own the long-running life loop; bypass `autonomy` safety/capability gates |
| Render emotion | `expression` | Atomic leds + OLED + voice + head + ears | Be a second planner |
| Move servos | `arduino_serial` contract + `animate` / `piservo` | Execute validated poses | Invent behavior |

## Conflict rules

1. **Speech in:** `speech` final text → `autonomy`. Autonomy may call `agent.step()` (`_try_agent_core_path`). If that fails, autonomy falls back to direct LLM. Agent-core does not poll the mic.
2. **Speech out:** `SpeechArbiter` in agent_core owns TTS enqueue for an agent turn. Autonomy `_speak_with_mood` is the fallback path only.
3. **Motion:** Companion goals pass `CompanionAutoExecuteGate` then `CompanionGoalExecutor`. On Raspberry Pi, `robot_execution_profiles.json` may enable real hardware. On PC, dry-run stays on.
4. **Lights / face / ears:** Only `expression` renders. Autonomy uses `/expression/express` (NeoPixel fallback). Interactions uses `output.via_expression` and forwards events to expression. `agent_core.ExpressionArbiter` is a **lease**, not the renderer.
5. **On conflict:** autonomy decides *whether*; expression decides *how it looks*; arduino_serial decides *how it moves*. Last writer without a lease loses.

## Runtime wiring

- Gateway mounts `autonomy`, then exposes the same `brain.agent` instance at `/agent/*`.
- HTTP between them is loopback on the same process; do not add a second orchestrator.
