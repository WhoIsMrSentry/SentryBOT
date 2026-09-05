# Gateway

SentryBOT'un tek FastAPI sürecinde tüm modül router'larını birleştiren ana giriş kapısıdır. Üretim modunda robot tek port üzerinden hizmet verir.

## Sorumluluklar

- Modül router'larını mount etme ve başlatma (`bootstrap`)
- Merkezi sağlık, durum ve derin sağlık kontrolü
- İsteğe bağlı API anahtarı ve rol tabanlı güvenlik katmanı
- Modüller arası kablolama: Arduino↔NeoPixel, VLM↔Autonomy, Speech↔Interactions vb.
- `resolve_gateway_base_url` ile loopback URL çözümleme (modüller tarafından kullanılır)

## Mimari (Güncel: 2026-08-20)

- Giriş noktası: `xGatewayService.py`
- **Bootstrap** (parçalanmış):
  - `services/bootstrap.py` - Ana orchestration
  - `services/bootstrap_config.py` - Config helpers, agent section merge, runtime keys
  - `services/bootstrap_ai.py` - AI/Expression modülleri (vlm_bridge, autonomy, agent_core, expression, voice, animate, oled_faces)
  - `services/bootstrap_hardware.py` - Hardware modülleri (arduino, camera, neopixel, piservo, esp_link)
  - `services/bootstrap_ops.py` - Platform modülleri (social_db, logs, notifier, runtime_console, state_manager, scheduler, config_center)
- Çekirdek router: `api/router.py`
- URL yardımcıları: `url.py`
- Konfigürasyon: `config/config.yml` + `config/agent.yaml` birleşimi

## Bootstrap Davranışı

`bootstrap(app, cfg)` modülleri `include.<module>` bayraklarına göre yükler.

**Config.yml'deki `include` anahtarları (eski isimler - bootstrap map'inde yeni yollara yönlendirilir):**

| Config Key | Gerçek Modül Yolu | Bootstrap Fonksiyonu |
|------------|-------------------|---------------------|
| `social_db` | `cognitive_memory` | `_include_social_db` |
| `arduino` | `arduino_serial` | `_include_arduino` |
| `esp_link` | `arduino_serial.transports.esp_transport` | `_include_esp_link` |
| `camera` | `camera` | `_include_camera` |
| `vlm_bridge` | `vlm_bridge` | `_include_vlm_bridge` |
| `neopixel` | `visual_output/neopixel` | `_include_neopixel` |
| `interactions` | `expression/interactions` | `_include_interactions` |
| `expression` | `expression` | `_include_expression` |
| `speak` | `voice/speak` | `_include_speak` |
| `wakeword` | `voice/wakeword` | `_include_wakeword` |
| `speech` | `voice/speech` | `_include_speech` |
| `ollama` | `ai_provider` | `_include_ollama` |
| `logs` | `runtime_console/logwrapper` | `_include_logs` |
| `animate` | `expression/animate` | `_include_animate` |
| `piservo` | `expression/piservo` | `_include_piservo` |
| `autonomy` | `autonomy` | `_include_autonomy` |
| `agent_core` | `agent_core` | `_include_agent_core` |
| `oled_faces` | `visual_output/oled_faces` | `_include_oled_faces` |
| `notifier` | `system_control/notifier` | `_include_notifier` |
| `runtime_console` | `runtime_console` | `_include_runtime_console` |

**Kritik modüller** (mount hatası `error` seviyesinde loglanır):
- `arduino`, `camera`, `autonomy`, `agent_core`, `speech`, `wakeword`, `speak`, `ollama`

**Import-tabanlı mount** (`_IMPORT_MODULES` - `system_control` alt modülleri):
- `telemetry` → `system_control.telemetry`
- `diagnostics` → `system_control.diagnostics`

**Opsiyonel mount** (ayrı fonksiyonlar):
- `state_manager` → `system_control/state_manager` (`_mount_state_manager`)
- `scheduler` → `system_control/scheduler` (`_mount_scheduler`)
- `config_center` → `system_control/config_center` (`_mount_config_center`)

**Bootstrap sonrası kablolama (wire functions):**
- `_wire_arduino_neopixel` - Arduino event `neopixel_request` → NeoRunner (ExpressionArbiter lease ile)
- `_wire_arduino_autonomy` - Arduino hardware events (cliff, bump, estop) → Autonomy brain
- `_wire_vlm_autonomy` - VLM bridge → Autonomy (vision context)
- `_wire_onsensor_vlm` - IMX500 bus → VLM bridge
- `_wire_head_arbiter` - HeadControlArbiter shared instance
- `_wire_animate_piservo` - Animate ↔ Piservo (ear channels)
- `_wire_interactions_piservo` - Interactions events → Piservo gestures
- `_wire_wakeword_interactions` - Wakeword → Interactions/NeoPixel
- `_wire_speech_interactions` - Speech → Interactions

## API

- `GET /healthz` — Startup durumu + modül bazlı sağlık
- `GET /status` — Include/start farkı
- `GET /health` — Derin sağlık taraması (httpx varsa)

Route listesi ayrı bir HTTP endpoint'i olarak sunulmaz; mount edilen tüm route'lar `api/router.py` içindeki `ROUTE_MANIFEST` sabitinde tutulur.

Mount edilen modüller kendi prefix'leri altında yayınlanır:
- `/arduino/*` - Arduino serial
- `/vlm/*` - VLM Bridge
- `/camera/*` - Camera
- `/neopixel/*` - Visual Output NeoPixel
- `/oled_faces/*` - Visual Output OLED
- `/expression/*` - Expression (semantic state, express tool)
- `/expression/animate/*` - Animate sequences
- `/expression/piservo/*` - Piservo ears
- `/expression/interactions/*` - Interactions rules
- `/voice/speech/*` - Speech ASR/DoA
- `/voice/speak/*` - Speak TTS
- `/voice/wakeword/*` - Wakeword
- `/autonomy/*` - Autonomy brain
- `/agent/*` - Agent Core
- `/cognitive/*` - Cognitive Memory (SocialDB)
- `/system/*` - System Control (telemetry, diagnostics, scheduler, state, config, notifier)
- `/ai_provider/*` - LLM Provider (Ollama)
- `/runtime_console/*` - TUI / Logs

## Konfigürasyon

`modules/gateway/config/config.yml`:
- `server.host`, `server.port` (default: 0.0.0.0:8080)
- `include.*` — Modül aç/kapa (yukarıdaki tablo)
- `security.enabled`, `security.api_key`, `security.admin_roles`
- `protected_get_prefixes` - Hassas GET uçları (camera, speech, state, telemetry, vlm, agent, autonomy, social)
- `arduino_neopixel_bridge.expression_lease` - Arduino NeoPixel bridge lease config

Güvenlik etkinse yazma uçları `X-API-Key` bekler; admin prefix'leri ek rol kontrolü uygular. `trust_loopback: true` ile localhost'tan key'siz erişim izin verilir.

## Çalıştırma

```bash
# Gateway tek başına
python -m modules.gateway.xGatewayService

# Üretim: run_robot.py (TUI + gateway + services)
python run_robot.py

# Docker
docker compose up --build -d
```

## İlişkiler

Gateway, projedeki modüller arası entegrasyonun omurgasıdır. Diğer modüller bağımsız servis olarak da çalışabilir (`uvicorn modules.xxx.xXxxService:create_app --factory`); ancak Pi5 üretim senaryosunda gateway tek süreç modelini sağlar.

**Önemli:** `config.yml` hala **eski modül isimlerini** kullanıyor (bootstrap `_include_map` yeni yollara yönlendirir). Gelecekte config.yml de yeni isimlere güncellenebilir.