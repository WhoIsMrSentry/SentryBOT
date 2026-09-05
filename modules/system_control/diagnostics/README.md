# Platform - Diagnostics

SentryBOT modüllerinin toplu sağlık kontrolünü yapan teşhis servisidir. Boot veya periyodik çalıştırmada sistem stabilitesini ölçer.

## Sorumluluklar

- Yapılandırılmış modüllere HTTP health/status ping
- Latency uyarıları (varsayılan >600ms)
- Opsiyonel self-heal (başarısız modüle POST)
- Opsiyonel notifier entegrasyonu (Telegram alert)
- Son rapor cache'i

## Mimari (Güncel: 2026-08-20)

- Giriş noktası: `xDiagnosticsService.py`
- **Motor**: `services/selftest.py` → `run_http_checks()`
- **Router**: `api/router.py`
- **Config**: `config_loader.py`

Gateway `_IMPORT_MODULES` ile `include.diagnostics=true` olduğunda mount edilir (`bootstrap_ops.py`). `platform/scheduler` job kind `diagnostics` bu servisi periyodik tetikleyebilir.

## Varsayılan Kontroller

`camera`, `arduino`, `neopixel`, `speech`, `speak`, `wakeword` — config yoksa bunlar kullanılır.

`speech/status` ve `speak/status` için yanıt gövdesi de doğrulanır (`model_ready`, `ready`).

## API (Gateway altında `/diagnostics/*`)

- `GET /diagnostics/healthz`
- `POST /diagnostics/run` — tüm kontrolleri çalıştırır, raporu cache'ler
- `GET /diagnostics/report` — son rapor

Rapor yapısı: `{ ok, failed[], degraded[], <modül>: { ok, latency_ms, ... } }`

## Konfigürasyon

`modules/system_control/diagnostics/config/config.yml`:

```yaml
gateway_port: 8080
checks:
  camera:
    enabled: true
    method: GET
    path: /camera/healthz
    critical: false
    heal:
      method: POST
      path: /camera/start
  arduino:
    enabled: true
    method: GET
    path: /arduino/healthz
    critical: true
  speech:
    enabled: true
    method: GET
    path: /speech/status
    critical: true
    heal:
      method: POST
      path: /speech/start
thresholds:
  default_timeout_ms: 1000
  default_latency_warn_ms: 600
self_heal:
  enabled: true
notify:
  enabled: false
  endpoint: /notify/test
```

## İlişkiler (Güncel Modül Yolları)

- `platform/scheduler`: periyodik diagnostics job (`kind: diagnostics`, `every_s: 3600`)
- `platform/notifier`: başarısızlık bildirimi (Telegram)
- `platform/state_manager`: operational state degraded/failed
- **Not:** `camera`, `arduino_serial`, `visual_output/neopixel`, `voice/speech`, `voice/speak`, `voice/wakeword` — config'de referans verilen modüller (eski isimlerle)

## Bilinen Sorunlar

1. **Self-Heal Döngü Riski** - Failed modüle `heal` POST atıyorsa, modül restart olur, diagnostics tekrar çalışır → sonsuz döngü. `heal` sonrası cooldown eksik.
2. **Hardcoded Module List** - Default checks `camera`, `arduino`, `neopixel`, `speech`, `speak`, `wakeword` kullanıyor. Yeni modül yolları (`visual_output/neopixel`, `voice/*`) config'de güncellenmeli.
3. **Latency Threshold** - 600ms sabit, modül bazlı threshold config'de olmalı.
4. **Notifier Entegrasyonu** - `notify.enabled: true` + `endpoint: /notify/test` ama `notifier` modülü mount edilmemişse hata verir. Dependency check eksik.