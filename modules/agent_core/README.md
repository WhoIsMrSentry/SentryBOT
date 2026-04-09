# Agent Core — Robotic AI Agent Module

**SentryBOT'un otonom ajan zekâ modülü.**

Sense → Think → Act döngüsünü yönetir. Sabit JSON kalıpları yerine Ollama destekli saf **Native Tool Calling (ReAct Döngüsü)** kullanarak robotun donanımını, hafızasını ve yeteneklerini sınırsız bir döngüde kontrol etmesini sağlar. 

## Modül Yapısı

```
modules/agent_core/
├── xAgentCoreService.py      # Servis başlatıcı (FastAPI + class)
├── config_loader.py          # config.yml okuyucu
├── config/
│   └── config.yml            # Modül ayarları
├── services/
│   ├── __init__.py           # Re-export proxy
│   ├── agent.py              # Ana orkestratör (Native ReAct Loop)
│   ├── safety_filter.py      # Donanım güvenlik sınırlayıcı (servolar vb.)
│   ├── memory.py             # SQLite epizodik bellek
│   ├── slam.py               # Topolojik harita + BFS yol bulma
│   ├── tools.py              # LLM araç tanımları (Ollama JSON Schema)
│   ├── world_state.py        # Sensör durumu
│   ├── sensor_loop.py        # Arka plan sensör okuyucu
│   └── idle_behavior.py      # Boşta kalma efektleri
├── architecture_agent_core.md# Mimari dokümantasyon
└── README.md                 # Bu dosya
```

## Özellikler

- **10-Step Cognitive Loop:** LLM bir işlem bitene kadar hafıza tarayabilir, etrafa bakabilir, sonra adım atabilir (art arda tool çağrısı).
- **Physical Safety First:** `ActionSafetyFilter` doğrudan donanım aletlerinin içine gömülüdür (Kafa çevirmeden önce direkt açı kontrolü yapılır).
- **Episodic Memory:** Robot konuştuğu her şeyi SQLite'a kaydeder ve `search_memory` tool'u ile geri çağırabilir.

## Kullanım

### AutonomyBrain ile (Entegre mod — üretim)
```python
# brain.py içinde otomatik başlatılır:
self.agent = AgentOrchestrator(agent_cfg, autonomy_client=self.client)
self.agent.start()
```

### Kütüphane olarak (ReAct Loop)
```python
from modules.agent_core import AgentOrchestrator
agent = AgentOrchestrator(config, autonomy_client=client)

# Ajan hafızasına bakar, neopixelleri ayarlar, 10 adıma kadar tool kullanır ve cevap döner.
result = agent.step("Ortamı tara ve bana kimlerin olduğunu söyle.")
print(result["text"])
```

## API Endpoint'leri

*(Executor ve router kaldırıldığı için API yapısı basitleştirildi)*

| Endpoint | Metod | Açıklama |
|---|---|---|
| `/healthz` | GET | Servis durumu (BUSY / IDLE) |
| `/step` | POST | Tek agent adımı (Native Tool Loop) |
| `/world_state` | GET | Anlık dünya durumu (pil vb.) |
| `/memory/search` | GET | Epizodik hafıza arama |
| `/slam/location` | GET | Topolojik konum |
| `/slam/pathfind` | GET | BFS yol bulma |

## Konfigürasyon (`config/config.yml`)

| Ayar | Açıklama |
|---|---|
| `agent.model` | Kullanılacak model (Örn: `llama3.2:3b`) |
| `agent.max_steps` | Bir döngüde LLM'in art arda yapabileceği tool call sayısı (Örn: 10) |

### .env / Ortam Değişkeni Override

Agent Core, `.env` değerlerini sırasıyla şu yollardan okuyabilir:
- `modules/agent_core/.env`
- `modules/ollama/.env`
- Proje kökü `.env`

Desteklenen anahtarlar:
- `AGENT_MODEL` veya `OLLAMA_MODEL`
- `AGENT_OLLAMA_BASE_URL` veya `OLLAMA_BASE_URL` veya `OLLAMA_HOST`
- `AGENT_COOLDOWN_S`

## Testler

```bash
# Proje ana dizininden:
$env:PYTHONPATH="."
pytest modules/agent_core/tests/ -v
```
