# Agent Core

SentryBOT'un konuşma odaklı ana ajan orkestratörüdür. `AgentOrchestrator`, kullanıcı isteğini veya olay tetiklerini alır; route eder, uygun araçları çalıştırır, bellek ve dünya durumunu kullanır ve son cevabı üretir.

## Sorumluluklar

- Tri-layer ajan akışı: Router/Planner, görev odaklı Sub-Agent'lar ve son Persona cevabı
- Tool-calling ve donanım güvenlik süzgeci (ExpressionArbiter lease sistemi)
- Epizodik bellek arama ve semantik sıralama (CognitiveMemory entegrasyonu)
- Dünya durumu ve SLAM konumu yüzeyi
- Eylem arbitrajı, ilerleme olayları ve gerçek zamanlı profil değiştirme

## Mimari (Güncel: 2026-08-20)

- Giriş noktası: `xAgentCoreService.py`
- Konfigürasyon: `config_loader.py` → merkezi `config/agent.yaml` (agent section)
- Ana orkestratör: `services/agent.py` → `AgentOrchestrator`
- **Yeni Tool Registry**: `services/tools/` (10 dosya: action_schemas, hardware_schemas, hardware_tools, http_client, motion_tools, perception_schemas, social_tools, tool_registry, tool_schemas, vision_tools)
- **Yeni Agent Parçaları**: `services/agent_context.py`, `agent_handlers.py`, `agent_memory_sync.py`, `agent_provider_parser.py`, `agent_streaming.py`, `agent_subagents.py`, `agent_turn.py`
- Yardımcı servisler: `memory.py`, `memory_consolidator.py`, `world_state.py`, `expression_arbiter.py`, `idle_behavior.py`, `tri_layer.py`
- **Arbiter'lar**: `action_arbiter.py` (aksiyon exclusive-lock hakemi), `speech_arbiter.py` (öncelikli TTS kuyruğu), `tool_execution_arbiter.py` (tool kaynak kilidi), `vision_arbiter.py` (VLM çağrı serileştirici)
- **Diğer**: `sensor_loop.py` (donanım sensör döngüsü), `semantic_index.py` (TF-IDF semantik router), `safety_filter.py` (girdi güvenlik filtresi), `slam.py`

Modül hem import edilebilir kütüphane hem de bağımsız FastAPI servisi olarak çalışır.

## Bağımlılıklar (Güncel)

- `autonomy`: Olay ve ajan koordinasyonu (brain.agent provider)
- `ai_provider` (eski `ollama`): LLM sağlayıcısı
- `system_control/config_center`: Merkezi config yükleme
- `runtime_console/logwrapper`: Merkezi log altyapısı
- `gateway`: URL çözümleme ve tek-port entegrasyon
- `common`: Ortak sözlükler (emotion_vocab), yardımcı fonksiyonlar
- `cognitive_memory` (eski `social_db`): Hafıza ve araç/kontrat yardımları
- `arduino_serial`: Donanım araçları için kontrat builder'lar
- `expression`: ExpressionArbiter (LED/servo/OLED lease)
- `vlm_bridge`: Vision tools için görüntü bağlamı

## API

Gateway altında `/agent/*` olarak yayınlanır.

### Core

- `GET /agent/healthz`
- `GET /agent/latency/latest`
- `GET /agent/latency/{trace_id}`
- `POST /agent/speech/interrupt`
- `POST /agent/step`
- `POST /agent/step_event`
- `POST /agent/step_stream`
- `POST /agent/route_preview`

### State and Memory

- `GET /agent/world_state`
- `GET /agent/memory/search`
- `GET /agent/slam/location`
- `GET /agent/slam/pathfind`

### Action Arbitration and Progress

- `GET /agent/actions/status`
- `GET /agent/arbiters/status`
- `GET /agent/arbiters/stream`
- `POST /agent/actions/queue`
- `POST /agent/actions/cancel`
- `POST /agent/progress`
- `POST /agent/events`
- `GET /agent/progress/latest`

### Runtime Profiles

- `GET /agent/profile`
- `POST /agent/profile/switch`

## Tool Registry (YENİ)

`services/tools/tool_registry.py` merkezi tool kayıt sistemi:
- **Hardware Tools**: servo, stepper, IMU, lazer, pose, IK, track, estop
- **Motion Tools**: animate sequences, piservo gestures
- **Perception Tools**: VLM track, face detect, scene analysis
- **Social Tools**: person upsert, chat episodes, preferences, relationships
- **Vision Tools**: capture frame, IMX500 status
- **Action Schemas**: JSON Schema tabanlı tool tanımları

Her tool: `schema` (JSON Schema), `handler` (async fn), `permissions` (hardware lease gerektirir mi?)

## Konfigürasyon

Bu modül merkezi `config/agent.yaml` içindeki `agent` bölümünü okur.

- `llm.provider`: `ollama` veya `google_ai_studio` (→ `ai_provider` modülü)
- `agent.model`, `agent.request_timeout`
- `tri_layer.*` (router, subagents, persona)
- `realtime_profile.*` (hız/kalite profilleri)
- `tools.hardware_lease_required`: donanım araçları için ExpressionArbiter lease

`ai_provider` profili aktifse model `qwen3.5:9b` olmalıdır.

## Kullanım

```python
from modules.agent_core.services.agent import AgentOrchestrator

agent = AgentOrchestrator(config, autonomy_client=client)
agent.start()
result = agent.step("Ortamı tara ve bana kimlerin burada olduğunu söyle.")
print(result["text"])
```

## İlgili Belgeler

- `architecture_agent_core.md`
- `MIGRATION_TRI_LAYER.md`
- `services/tools/__init__.py` docstring (tool registry detayları)