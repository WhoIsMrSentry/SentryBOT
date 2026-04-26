# VLM + Tri-Layer Agent Workflow

Bu dokuman, VLM-oncelikli 3 katmanli agent akisinin nasil calistigini ornek bir senaryo ile ozetler.

- Primary model: `qwen3.5:9b`
- Fallback model: `qwen3.5:9b`
- Remote Ollama endpoint semasi: `http://<remote-ollama-host>:11434/api/chat`

## Sequence Diagram (Ornek Senaryo)

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant L1 as AgentCore Layer-1 Router
    participant V as VLM Bridge
    participant O as Remote Ollama
    participant L2 as Layer-2 SubAgents
    participant L3 as Layer-3 Main Persona
    participant A as Autonomy

    U->>L1: Ortami anlat
    L1->>L2: Route modules vlm_bridge + autonomy
    L2->>V: Analyze latest scene context
    V->>O: POST /api/chat\nmodel=gemma-4-26B-A4B
    O-->>V: Scene summary text

    alt Primary model missing or first-call error
        V->>O: Retry /api/chat\nmodel=qwen3.5:9b
        O-->>V: Fallback summary
    end

    V-->>L2: Structured scene report
    L2->>A: Propose actions with safety bounds
    A-->>L2: Action candidates
    L2->>L3: Merge sub-agent outputs
    L3-->>U: Final response + optional actions
```

## Kisa Notlar

1. Layer-1 sadece yonlendirme yapar, agir isleme girmez.
2. Layer-2 sub-agentlar dar kapsamli tool set ile calisir.
3. Layer-3 ana persona tek bir tutarli cevap uretir.
4. Endpoint `/api/tags` gelirse istemci bunu otomatik `/api/chat` olarak normalize eder.
