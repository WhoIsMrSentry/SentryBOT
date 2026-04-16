# Agent Core — Robotic AI Agent Module

**SentryBOT'un otonom ajan zekâ modülü.**

Sense -> Think -> Act dongusunu, tek Ollama modeli ile calisan **3 katmanli agent yapisiyla** yonetir:
1) Router/Planner
2) Modul bazli Sub-Agent'lar
3) Main Persona (son cevaplayici)

Her katman ayni modeli kullanir, ancak farkli sorumluluk ve prompt profiline sahiptir.

Varsayilan politika:
- VLM-primary tek model: `gemma-4-26B-A4B`
- CLM fallback: `qwen3.5:8b` (model yoksa veya ilk cagri hatasinda)
- Provider `google_ai_studio` secilirse Google API istemcisi kullanilir ve sinirli tool-calling denemesi yapilir.

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
│   ├── idle_behavior.py      # Boşta kalma efektleri
│   └── tri_layer.py          # Router + sub-agent profil tanimlari
├── architecture_agent_core.md# Mimari dokümantasyon
└── README.md                 # Bu dosya
```

## Özellikler

- **3-Layer Agent Pipeline:** Katman-1 istegi modul sub-agent'lara yonlendirir, Katman-2 uzman sub-agent'lar araci calistirir, Katman-3 main persona tek ve tutarli cevap uretir.
- **Tek Model Politikasi:** Router, sub-agent ve persona katmanlari ayni Ollama modeli uzerinden calisir.
- **Low-Latency Router:** Varsayilan keyword tabanli yonlendirme ek gecikme olmadan calisir.
- **Semantic Router:** Router artık token benzerliğini de hesaba katar; tam eşleşmeyen ama yakın isteklerde daha doğru modül seçimi sağlar.
- **Physical Safety First:** `ActionSafetyFilter` doğrudan donanım aletlerinin içine gömülüdür (Kafa çevirmeden önce direkt açı kontrolü yapılır).
- **Episodic Memory:** Robot konuştuğu her şeyi SQLite'a kaydeder ve `search_memory` tool'u ile geri çağırabilir.
- **Semantic Memory Ranking:** Arama sonuçları yalnızca eşleşme değil, alaka puanına göre sıralanır.
- **Runtime SLAM Learning:** Ajan yeni konum, bağlantı ve takma adları çalışma anında haritaya ekleyebilir.

## Bu Modül Ne Yapar?
- Gelen isteği planlar, uygun sub-agent'lara yönlendirir ve son cevabı üretir.
- Kısa süreli ve uzun süreli hafızayı yönetir.
- Topolojik harita üzerinden konum bulur ve yol planlar.
- Yeni araçları ve güvenlik sınırlarını LLM kullanımına sunar.

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

# Ajan tri-layer akista sub-agent'lari calistirir ve final personadan tek cevap dondurur.
result = agent.step("Ortamı tara ve bana kimlerin olduğunu söyle.")
print(result["text"])
```

## API Endpoint'leri

*(Executor ve router kaldırıldığı için API yapısı basitleştirildi)*

| Endpoint | Metod | Açıklama |
|---|---|---|
| `/healthz` | GET | Servis durumu (BUSY / IDLE) |
| `/step` | POST | Tek agent adımı (Native Tool Loop) |
| `/route_preview` | POST | Tri-layer router secimini onizleme |
| `/world_state` | GET | Anlık dünya durumu (pil vb.) |
| `/memory/search` | GET | Epizodik hafıza arama |
| `/slam/location` | GET | Topolojik konum |
| `/slam/pathfind` | GET | BFS yol bulma |

`/memory/search` sonuçları artık önem puanına göre sıralanır. SLAM tarafı ise yeni düğüm, bağlantı ve alias öğrenmeyi destekler.

## Konfigürasyon (`config/config.yml`)

| Ayar | Açıklama |
|---|---|
| `agent.model` | Kullanılacak model (Örn: `llama3.2:3b`) |
| `agent.request_timeout` | Ollama istemci timeout degeri (sn) |
| `agent.max_steps` | Legacy native loop maksimum adım sayısı |
| `tri_layer.enabled` | 3 katmanli mimari acik/kapali |
| `tri_layer.router.max_subagents` | Bir istek icin secilecek sub-agent sayisi |
| `tri_layer.subagent.max_steps` | Her sub-agent icin maksimum tool loop |
| `tri_layer.persona.num_predict` | Final persona katmaninda token hedefi |
| `llm.clm_fallback_enabled` | CLM fallback acik/kapali |
| `llm.clm_fallback_model` | Fallback model adi |
| `llm.fallback_on_missing_model` | Primary model yoksa fallback |
| `llm.fallback_on_error` | Primary model ilk hata alirsa fallback |

### .env / Ortam Değişkeni Override

Agent Core, `.env` değerlerini sırasıyla şu yollardan okuyabilir:
- `modules/agent_core/.env`
- `modules/ollama/.env`
- Proje kökü `.env`

Desteklenen anahtarlar:
- `AGENT_MODEL` veya `OLLAMA_MODEL`
- `LLM_PROVIDER` (tri-layer icin `ollama` onerilir)
- `AGENT_OLLAMA_BASE_URL` veya `OLLAMA_BASE_URL` veya `OLLAMA_HOST`
- `AGENT_OLLAMA_REQUEST_TIMEOUT` veya `OLLAMA_REQUEST_TIMEOUT`
- `AGENT_COOLDOWN_S`
- `AGENT_MAX_STEPS`
- `AGENT_TRI_LAYER_ENABLED`
- `AGENT_ROUTER_MAX_SUBAGENTS`
- `AGENT_SUBAGENT_MAX_STEPS`
- `AGENT_PERSONA_NUM_PREDICT`
- `AGENT_CLM_FALLBACK_ENABLED`
- `AGENT_CLM_FALLBACK_MODEL`
- `AGENT_FALLBACK_ON_MISSING_MODEL`
- `AGENT_FALLBACK_ON_ERROR`

## Testler

```bash
# Proje ana dizininden:
$env:PYTHONPATH="."
pytest modules/agent_core/tests/ -v
```

## Migration

Tri-layer gecisi ve remote Ollama kurulumu icin:

- `modules/agent_core/MIGRATION_TRI_LAYER.md`
