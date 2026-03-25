# Agent Core — Robotic AI Agent Module

**SentryBOT'un otonom ajan zekâ modülü.**

Sense → Think → Act döngüsünü yönetir. LLM ile ReAct (Reasoning + Acting) aracılığıyla multi-turn tool calling yapar, JSON çıktısını doğrular, güvenlik filtresi uygular ve eylemleri donanıma iletir.

## Modül Yapısı

```
modules/agent_core/
├── xAgentCoreService.py      # Servis başlatıcı (FastAPI + class)
├── config_loader.py           # config.yml okuyucu
├── config/
│   └── config.yml             # Modül ayarları
├── services/
│   ├── __init__.py            # Re-export proxy
│   ├── agent.py               # Ana orkestratör (ReAct Loop)
│   ├── validator.py           # JSON şema doğrulayıcı
│   ├── safety_filter.py       # Donanım güvenlik sınırlayıcı
│   ├── planner.py             # Plan → görev kuyruğu dönüştürücü
│   ├── executor.py            # Durum makinesi (State Machine)
│   ├── router.py              # 22 aksiyon tipi → HAL yönlendirici
│   ├── memory.py              # SQLite epizodik bellek
│   ├── slam.py                # Topolojik harita + BFS yol bulma
│   ├── tools.py               # LLM araç tanımları (4 araç)
│   ├── world_state.py         # Chrono-farkındalık + sensör durumu
│   ├── sensor_loop.py         # Arka plan sensör okuyucu (Thread)
│   └── idle_behavior.py       # Boşta kalma nefes efekti
├── architecture_agent_core.md # Mimari dokümantasyon
└── README.md                  # Bu dosya
```

## Kullanım

### AutonomyBrain ile (Entegre mod — üretim)
```python
# brain.py içinde otomatik başlatılır:
self.agent = AgentOrchestrator(agent_cfg, autonomy_client=self.client)
self.agent.start()
```

### Bağımsız servis olarak
```bash
python -m modules.agent_core.xAgentCoreService
# → http://localhost:8120 (FastAPI)
```

### Kütüphane olarak
```python
from modules.agent_core import AgentOrchestrator
agent = AgentOrchestrator(config, autonomy_client=client)
agent.start()
result = agent.step("Mutfağa git")
```

## API Endpoint'leri

| Endpoint | Metod | Açıklama |
|---|---|---|
| `/healthz` | GET | Servis durumu + executor state |
| `/step` | POST | Tek agent adımı (ReAct + Tool Calling) |
| `/world_state` | GET | Anlık dünya durumu |
| `/memory/search` | GET | Epizodik hafıza arama |
| `/slam/location` | GET | Topolojik konum |
| `/slam/pathfind` | GET | BFS yol bulma |
| `/executor/interrupt` | POST | Plan kuyruğu durdur |
| `/executor/resume` | POST | Devam ettir |

## Konfigürasyon

Tüm ayarlar `config/config.yml` üzerinden yönetilir. Ortam değişkenleri ile override edilebilir:

| Env | Açıklama |
|---|---|
| `AGENT_MODEL` | LLM model adı |
| `AGENT_COOLDOWN_S` | LLM çağrı aralığı |

## Testler

```bash
pytest modules/agent_core/tests/ -v
```
