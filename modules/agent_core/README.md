# Agent Core

SentryBOT'un konuşma odaklı ana ajan orkestratörüdür. `AgentOrchestrator`, kullanıcı isteğini veya olay tetiklerini alır; route eder, uygun araçları çalıştırır, bellek ve dünya durumunu kullanır ve son cevabı üretir.

## Sorumluluklar

- Tri-layer ajan akışı: router/planner, görev odaklı alt yetenekler ve son persona cevabı
- Tool-calling ve donanım güvenlik süzgeci
- Epizodik bellek arama ve semantik sıralama
- Dünya durumu, SLAM konumu ve yol bulma yüzeyi
- Eylem arbitrajı, ilerleme olayları ve gerçek zamanlı profil değiştirme

## Mimari

- Giriş noktası: `xAgentCoreService.py`
- Konfigürasyon: `config_loader.py` üzerinden merkezi `config/agent.yaml`
- Ana orkestratör: `services/agent.py`
- Yardımcı servisler: `memory.py`, `semantic_index.py`, `world_state.py`, `slam.py`, `action_arbiter.py`, `progress.py`, `tri_layer.py`

Modül hem import edilebilir kütüphane hem de bağımsız FastAPI servisi olarak çalışır.

## Bağımlılıklar

- `autonomy`: olay ve ajan koordinasyonu
- `ollama` ve opsiyonel `google_ai_studio`: LLM sağlayıcısı
- `config_center`: merkezi config yükleme
- `logwrapper`: merkezi log altyapısı
- `gateway`: URL çözümleme ve tek-port entegrasyon
- `common`, `social_db`, `arduino_serial`: ortak sözlükler, hafıza ve araç/kontrat yardımları

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

## Konfigürasyon

Bu modül merkezi `config/agent.yaml` içindeki ilgili bölümleri okur ve çalışma politikasını zorunlu hale getirir.

- `llm.provider`: `ollama` veya `google_ai_studio`
- `agent.model`, `agent.request_timeout`
- `tri_layer.*`
- `realtime_profile.*`
- `ollama.base_url` veya Google AI Studio ayarları

`ollama` profili aktifse model zorunlu olarak `qwen3.5:9b` olmalıdır. Google profili seçildiğinde de tek-model çalışma modu korunur.

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
