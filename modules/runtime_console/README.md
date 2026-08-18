# Runtime Console

SentryBOT'un terminal kontrol merkezidir. TUI ile robot sürecini başlatır, logları izler ve gateway snapshot'larını gösterir. Otonom karar üretmez.

## Sorumluluklar

- `scripts/run_robot.py` alt sürecini yönetme (`RobotProcess`)
- Log kuyruğu, kanal sınıflandırma, health-check gürültü filtreleme
- Config YAML görüntüleme/düzenleme, proje araması
- Companion / expression / camera snapshot sekmeleri
- In-process `RuntimeEventBus` (HTTP kuyruğu; gateway mount etmez)

## Mimari

- Birleşik launcher: kök `sentrybot.py` → `system_info_tui` + `tui_v2.main`
- TUI v2: `tui_v2.py` (`run_tui`, `main`)
- Alt süreç: `services/robot_process.py`
- Render/input: `services/screen_renderers.py`, `services/input_handler.py`
- Modeller: `services/models.py` (`TABS`, `Snapshot`, `UIState`)
- Eski panel/event bus: `dashboard.py`, `event_bus.py`, `renderer.py`
- HTTP: `api/router.py` (`/runtime_console/healthz`, `/events`) — gateway bootstrap'ta mount edilmez
- Log entegrasyonu: `logwrapper` `RuntimeConsoleLogHandler` kullanır

Kısa yollar: `apps/run_robot_tui.py` (`--run`), `apps/sentrybot_tui.py`.

## TUI Sekmeler

`Overview`, `Logs`, `Signals`, `Config`, `Search`, `Companion`, `Expression`, `Camera`, `Help`

## API (bağımsız; gateway dahil değil)

- `GET /runtime_console/healthz` — event bus uzunluğu
- `GET /runtime_console/events?limit=20` — kuyruk kuyruğu

## Konfigürasyon

`config/config.yml`:
- `mode` (`dashboard` / compact)
- `hidden_paths` — tekrarlayan HTTP gürültüsü
- `channels` — CORE / AUDIO / TTS / VISION / AI / FACE / MOVE / MEMORY

`config/tui.yml` — TUI görünüm bayrakları (`hide_old_runtime_console`).

## İlişkiler

- `sentrybot.py`: birleşik giriş
- `scripts/run_robot.py`: gateway/uvicorn alt süreç
- `logwrapper`: TUI log handler
- Gateway HTTP: health, companion, expression, camera snapshot'ları

Operatörün yerel gözlem ve süreç kontrol katmanıdır.
