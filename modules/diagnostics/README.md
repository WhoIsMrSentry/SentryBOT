# Diagnostics

SentryBOT modüllerinin toplu sağlık kontrolünü yapan teşhis servisidir. Boot veya periyodik çalıştırmada sistem stabilitesini ölçer.

## Sorumluluklar

- Yapılandırılmış modüllere HTTP health/status ping
- Latency uyarıları (varsayılan >600ms)
- Opsiyonel self-heal (başarısız modüle POST)
- Opsiyonel notifier entegrasyonu
- Son rapor cache'i

## Mimari

- Giriş noktası: `xDiagnosticsService.py`
- Motor: `services/selftest.py` (`run_http_checks`)
- Router: `api/router.py`

Gateway `_IMPORT_MODULES` ile `include.diagnostics=true` olduğunda mount edilir. `scheduler` job kind `diagnostics` bu servisi periyodik tetikleyebilir.

## Varsayılan Kontroller

`camera`, `arduino`, `neopixel`, `speech`, `speak`, `wakeword` — config yoksa bunlar kullanılır.

`speech/status` ve `speak/status` için yanıt gövdesi de doğrulanır (`model_ready`, `ready`).

## API (Gateway altında `/diagnostics/*`)

- `GET /diagnostics/healthz`
- `POST /diagnostics/run` — tüm kontrolleri çalıştırır, raporu cache'ler
- `GET /diagnostics/report` — son rapor

Rapor yapısı: `{ ok, failed[], degraded[], <modül>: { ok, latency_ms, ... } }`

## Konfigürasyon

`config/config.yml`:
```yaml
gateway_port: 8080
checks:
  arduino:
    enabled: true
    method: GET
    path: /arduino/healthz
    critical: true
    heal:
      method: POST
      path: /speech/start
thresholds:
  default_timeout_ms: 1000
  default_latency_warn_ms: 600
self_heal:
  enabled: false
notify:
  enabled: false
  endpoint: /notify/test
```

## İlişkiler

- `scheduler`: periyodik diagnostics job
- `notifier`: başarısızlık bildirimi
- Otonomlukta operasyonel güvenilirlik katmanıdır; karar üretmez
