# Agent Core — Mimari Dokümantasyon

## Genel Bakış

Agent Core, SentryBOT'un otonom karar verme, çevreyi algılama ve alet (tool) kullanma katmanıdır. Geleneksel ve katı yapısal çıktılar (structured outputs) yerine, saf bir **Native Tool Calling (ReAct)** döngüsü kullanarak LLM'in ardışık olarak aletleri kullanıp mantık yürütmesine olanak tanır. AutonomyBrain içine subsistem olarak entegre olur.

## Modül Yapısı

```
modules/agent_core/
├── xAgentCoreService.py      # Servis başlatıcı
├── config_loader.py          # config.yml okuyucu
├── config/
│   └── config.yml            # Modül ayarları
├── services/
│   ├── __init__.py           # Re-export proxy
│   ├── agent.py              # Ana orkestratör (Native ReAct Loop)
│   ├── safety_filter.py      # Donanım güvenlik sınırlayıcı (servolar vb.)
│   ├── memory.py             # SQLite epizodik bellek (Kalıcı bellek)
│   ├── slam.py               # Topolojik harita + BFS yol bulma
│   ├── tools.py              # LLM araç tanımları (10 adet Native Tool)
│   ├── world_state.py        # Sensör durumu (Pil, ultrasonik vb.)
│   ├── sensor_loop.py        # Arka plan sensör okuyucu (Thread)
│   └── idle_behavior.py      # Boşta kalma nefes efekti
├── architecture_agent_core.md# Mimari dokümantasyon
└── README.md                 # Genel bilgi
```

## Veri Akışı (Native ReAct Loop)

```mermaid
flowchart TD
    MIC[Mikrofon / Sensörler] --> AB[AutonomyBrain]
    AB -->|agent.step| AO[AgentOrchestrator]
    
    subgraph AgentCore["Agent Core Pipeline"]
        AO --> WS[WorldState (Farkındalık)]
        WS --> LLM[LLM Reasoning (Ollama)]
        
        LLM <-->|10-Adımlı ReAct Tool Döngüsü| TR[ToolRegistry]
        TR --> SF[SafetyFilter (Korumalar)]
        
        TR --> MEM[EpisodicMemory (Kayıt / Arama)]
        TR --> SLAM[TopologicalMap (Yol Bulma)]
    end
    
    SF --> HAL[HAL Layer (HTTP via ServiceClient)]
    
    subgraph HALLayer["Hardware Abstraction Layer"]
        HAL --> SS[ServoService (move_head)]
        HAL --> LS[LightsService (set_lights)]
        HAL --> MS[MotorService / AudioService]
    end
    
    SS -->|/arduino/request| ARD[Serial Gateway]
```

## Modüller Arası Etkileşim

| Modül | Agent Core ile İlişki |
|---|---|
| `autonomy` | Agent Core'u başlatır. Günlük sohbeti yönetir, karmaşık işlerde `agent.step()`'i çağırır. |
| `ollama` | Agent döngüsü (`ollama.chat(tools=...)`) için doğrudan Python kütüphanesi kullanılır. |
| `hardware` | `ServiceClient` üzerinden HTTP ile tetiklenir, Agent Core donanıma doğrudan bağlanmaz. |

## Tasarım Kararları

### Neden Native Tool Calling?
Eski mimari, LLM'i sabit bir JSON objesi üretmeye (`validator` -> `planner` -> `executor` -> `router`) zorluyordu. Bu durum ajanın doğal mantık yürütmesini ve esnekliğini kısıtlıyordu (kilitliyordu). Yeni yapıda ajan `tools.py` içerisindeki Python fonksiyonlarını (örn: `move_head`, `search_memory`) bir döngü içerisinde defalarca kullanabilir ve görevleri daha özgür bir şekilde yerine getirir.
