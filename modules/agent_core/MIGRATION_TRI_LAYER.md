# Agent Core Tri-Layer Migration Notes

This note explains how to migrate from the previous single-loop orchestration to the new tri-layer model.

## What Changed

1. Layer 1: Router/Planner selects module-level sub-agents.
2. Layer 2: Sub-agents execute focused reasoning with limited tool sets.
3. Layer 3: Main persona synthesizes the final user-facing response.

All three layers run on one Ollama model.

## New Config Keys

Use only `config/agent.yaml`.

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

Strict mode keeps runtime behavior in YAML.

Only path override is supported:
- `AGENT_CFG=/absolute/path/to/agent.yaml`

## Remote Ollama Server (Single Model)

Set one model and one remote base URL:

- `agent.model: gemma4:26b`
- `agent.ollama_base_url: http://<remote-ollama-host>:11434`

The same model is used by router, sub-agents, and main persona.

Fallback policy (CLM): disabled in strict single-model mode.

## API Additions

- `POST /route_preview` returns selected sub-agents for a query.

## Backward Compatibility

- If no sub-agent is selected, orchestrator falls back to the native legacy tool loop.
- Existing `agent.step()` call sites continue to work without changes.
