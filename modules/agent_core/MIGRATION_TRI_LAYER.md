# Agent Core Tri-Layer Migration Notes

This note explains how to migrate from the previous single-loop orchestration to the new tri-layer model.

## What Changed

1. Layer 1: Router/Planner selects module-level sub-agents.
2. Layer 2: Sub-agents execute focused reasoning with limited tool sets.
3. Layer 3: Main persona synthesizes the final user-facing response.

All three layers run on one Ollama model.

## New Config Keys

Use either `config/agent.yaml` or `modules/agent_core/config/config.yml`.

```yaml
tri_layer:
  enabled: true
  router:
    max_subagents: 2
    default_modules: [autonomy, agent_core]
  subagent:
    max_steps: 2
  persona:
    num_predict: 220
```

## Environment Overrides

- `AGENT_TRI_LAYER_ENABLED=true|false`
- `AGENT_ROUTER_MAX_SUBAGENTS=2`
- `AGENT_SUBAGENT_MAX_STEPS=2`
- `AGENT_PERSONA_NUM_PREDICT=220`
- `AGENT_MAX_STEPS=6`
- `LLM_PROVIDER=ollama`
- `AGENT_OLLAMA_REQUEST_TIMEOUT=60`
- `AGENT_OLLAMA_BASE_URL=http://<remote-ip>:11434`

## Remote Ollama Server (Single Model)

Set one model and one remote base URL:

- `AGENT_MODEL=gemma-4-26B-A4B`
- `AGENT_OLLAMA_BASE_URL=http://<remote-ollama-host>:11434`

The same model is used by router, sub-agents, and main persona.

Fallback policy (CLM):

- `AGENT_CLM_FALLBACK_ENABLED=true`
- `AGENT_CLM_FALLBACK_MODEL=qwen3.5:8b`
- `AGENT_FALLBACK_ON_MISSING_MODEL=true`
- `AGENT_FALLBACK_ON_ERROR=true`

## API Additions

- `POST /route_preview` returns selected sub-agents for a query.

## Backward Compatibility

- If no sub-agent is selected, orchestrator falls back to the native legacy tool loop.
- Existing `agent.step()` call sites continue to work without changes.
