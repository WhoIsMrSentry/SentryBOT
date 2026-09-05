# Ops - Runtime Console

SentryBOT'un terminal kontrol merkezidir. TUI ile robot sürecini başlatır, logları izler ve gateway snapshot'larını gösterir. Otonom karar üretmez.

## Sorumluluklar

- **Unified Launcher**: `sentrybot.py` entry point → **TAŞINMALI: `ops/console/__main__.py`**
- `scripts/run_robot.py` alt sürecini yönetme (`RobotProcess`)
- Log kuyruğu, kanal sınıflandırma, health-check gürültü filtreleme
- Config YAML görüntüleme/düzenleme, proje araması
- Companion / expression / camera snapshot sekmeleri
- In-process `RuntimeEventBus` (HTTP kuyruğu; gateway `include.runtime_console=true` ile mount edilir)
- Log entegrasyonu: `logwrapper` `RuntimeConsoleLogHandler` kullanır

## Mimari (Güncel: 2026-08-20)

- **Launcher**: `sentrybot.py` (kök) → `system_info_tui` + `tui_v2.main` — **TAŞINMALI**
- **TUI v2**: `tui_v2.py` (`run_tui`, `main`) — artık ~221 satır; sekme render'ları `services/tab_renderers/` (overview/logs/media/companion/tools), yardımcılar `services/console_helpers.py` / `console_formatting.py` / `console_constants.py` / `console_types.py` ailesine bölündü
- **Alt Süreç**: `services/robot_process.py` → `RobotProcess` (subprocess manager)
- **System Info**: `services/system_info_collector.py` + `services/system_info_hardware.py` (toplama + donanım tespiti)
- **Render/Input**: `services/screen_renderers.py`, `services/input_handler.py`
- **Modeller**: `services/models.py` → `TABS`, `Snapshot`, `UIState` (~145 satır)
- **Eski Panel/Event Bus**: `dashboard.py`, `event_bus.py`, `renderer.py` (deprecated, temizlenmeli)
- **HTTP**: `api/router.py` (`/runtime_console/healthz`, `/events`) — gateway `include.runtime_console` açıkken mount
- **Log Entegrasyonu**: `logwrapper` → `RuntimeConsoleLogHandler` (memory handler → TUI)

## TUI Sekmeler

`Overview`, `Logs`, `Signals`, `Config`, `Search`, `Companion`, `Expression`, `Camera`, `Help`

## API (Gateway altında `/runtime_console/*`)

- `GET /runtime_console/healthz` — event bus uzunluğu
- `GET /runtime_console/events?limit=20` — kuyruk kuyruğu

## Konfigürasyon

`modules/runtime_console/config/config.yml`:
- `mode` (`dashboard` / `compact`)
- `hidden_paths` — tekrarlayan HTTP gürültüsü (healthz, metrics, etc.)
- `channels` — `CORE`, `AUDIO`, `TTS`, `VISION`, `AI`, `FACE`, `MOVE`, `MEMORY`

`config/tui.yml` — TUI görünüm bayrakları (`hide_old_runtime_console`).

## İlişkiler (Güncel Modül Yolları)

- `sentrybot.py` → **UNIFIED LAUNCHER** (kök dizinde, taşınmalı)
- `scripts/run_robot.py` — gateway/uvicorn alt süreç
- `runtime_console/logwrapper` — TUI log handler
- Gateway HTTP: health, companion, expression, camera snapshot'ları
- `platform/telemetry` → metrics display
- `platform/diagnostics` → health report display

## ⚠️ KRİTİK SORUNLAR

### 1. **İki Process Manager Çakışması**
| Bileşen | Açıklama |
|---------|----------|
| `sentrybot.py` (kök) | `subprocess.Popen(["python", "run_robot.py"])` başlatır |
| `runtime_console/services/robot_process.py` | `RobotProcess` sınıfı aynı `run_robot.py`'yi manage eder |

**Sonuç:** `sentrybot.py` doğrudan subprocess başlatıyor, `runtime_console` da `RobotProcess` ile aynı işi yapıyor. **İki process manager** → port çakışması (8080), PID confusion, log duplication.

**Çözüm:** `sentrybot.py` **SİLİNMELİ** veya `ops/console/__main__.py`'ye taşınmalı. `python -m ops.console` tek entry point olmalı. `RobotProcess` singleton pattern.

### 2. ~~**God Classes (SRP İhlali)**~~ **ÇÖZÜLDÜ**
Eski god-class yapısı parçalandı: `tui_v2.py` 5874 → **~221 satır** (render'lar `services/tab_renderers/`, yardımcılar `console_*` ailesi), `system_info_tui.py` 7811 → **~246 satır** (`services/system_info_collector.py` + `services/system_info_hardware.py`), `services/models.py` 1044 → **~145 satır**.

### 3. **Eski Kod Temizlenmeli**
- `dashboard.py`, `event_bus.py`, `renderer.py` — `tui_v2.py` ile duplicate, **SİLİNMELİ**
- `services/input_handler.py` — `tui_v2.py` içinde input handling var, duplicate

### 4. **Logwrapper Entegrasyonu Zayıf**
- `logwrapper` `RuntimeConsoleLogHandler` memory buffer → TUI
- Buffer boyutu sınırsız, memory leak riski
- Log rotation (`logwrapper/run_rotator.py`) TUI'ya yansımıyor

### 5. **Config UI Read-Only**
- `Config` sekmesinde YAML görüntüleme var ama **düzenleme/yazma yok** (PUT `/config/set` gateway'de var ama TUI'den çağrılmıyor)

## Önerilen Yeniden Yapılandırma (TARİHÎ)

> **Not:** Bu planın büyük bölümü `services/tab_renderers/` + `console_*` yapısıyla uygulandı (`tui_v2.py`, `system_info_tui.py`, `models.py` parçalamaları tamamlandı). Aşağıdaki plan geçmiş kayıt olarak korunmaktadır; güncel yapı için yukarıdaki "Mimari" bölümüne bakın.

### Yeni Modül Yapısı: `ops/console/`

```
modules/ops/console/
├── __main__.py              # Entry point (eski sentrybot.py)
├── app.py                   # Main TUI loop (eski tui_v2.py → ~500 satır)
├── process_manager.py       # RobotProcess singleton (eski robot_process.py)
├── log_integration.py       # Logwrapper handler + buffer management
├── config_ui.py             # Config YAML edit (PUT /config/set)
├── tabs/
│   ├── __init__.py
│   ├── overview.py          # System status, health
│   ├── logs.py              # Log viewer + filter
│   ├── signals.py           # Event bus monitor
│   ├── config.py            # Config viewer + editor
│   ├── search.py            # Project search
│   ├── companion.py         # Companion status
│   ├── expression.py        # Expression state
│   ├── camera.py            # Camera snapshot + stream
│   └── help.py              # Shortcuts
├── render/
│   ├── __init__.py
│   ├── base.py              # Base renderer
│   ├── panels.py            # Panel components
│   └── ascii_helpers.py     # ASCII-safe drawing
├── input/
│   ├── __init__.py
│   └── handler.py           # Key/input handling
├── snapshot/
│   ├── __init__.py
│   ├── collector.py         # Gateway snapshot aggregation
│   └── formatters.py        # Tab-specific formatting
├── models/
│   ├── __init__.py
│   ├── tabs.py              # TABS enum
│   ├── snapshot.py          # Snapshot dataclass
│   ├── ui.py                # UIState
│   └── channels.py          # ChannelConfig
├── system_info/
│   ├── __init__.py
│   ├── collector.py         # System metrics collection
│   ├── hardware.py          # Hardware detection (GPU, sensors)
│   └── formatter.py         # Display formatting
└── config/
    ├── config.yml
    └── tui.yml
```

### Taşıma Planı

1. `sentrybot.py` → `ops/console/__main__.py` (entry point)
2. `runtime_console/` → `ops/console/` (klasör taşıma)
3. `tui_v2.py` → `app.py` + `tabs/` + `render/` + `input/` (parçalama)
4. `system_info_tui.py` → `system_info/collector.py` + `hardware.py` + `formatter.py`
5. `services/models.py` → `models/` altına bölme
6. Eski dosyalar sil: `dashboard.py`, `event_bus.py`, `renderer.py`, `services/input_handler.py`
7. `logwrapper` → `ops/console/log_integration.py` (buffer limit, rotation sync)
8. Gateway mount path: `/runtime_console/*` → `/ops/console/*` (veya aynı kalsın, internal path değişmez)

## Testler

- `tests/modules/runtime_console/test_smoke.py` — basic import, event bus, renderer
- `tests/modules/runtime_console/test_tui_v2.py` — TUI parsing, rendering, ASCII safety
- `tests/modules/runtime_console/test_pi_import_time_quiet.py` — startup import time
- `tests/modules/runtime_console/logwrapper/test_*.py` — logwrapper tests

Tüm testler **733 passed** ✅