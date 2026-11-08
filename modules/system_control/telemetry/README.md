# Platform - Telemetry

SentryBOT'un hafif metrik toplayıcısıdır. Thread-safe in-memory counter/gauge/summary registry tutar; Prometheus scrape ve JSON snapshot formatında sunar.

## Sorumluluklar

- Olay sayaçları ve opsiyonel gecikme özeti (`POST /telemetry/events`, max 64 benzersiz olay tipi + `event_other_total` taşma kovası)
- Prometheus `text/plain; version=0.0.4` metrik çıktısı (`GET /telemetry/metrics`, `exporter.type: builtin|none` destekli)
- JSON anlık metrik ve donanım özeti (`GET /telemetry/snapshot`)
- `threading.RLock` korumalı in-memory `Registry` ve kayan pencereli `Summary` (`p50`, `p95`, `max`, `avg`)
- Host gauges (`cpu_temp_c`, `cpu_load_1m`, `mem_available_mb`, `disk_free_gb`, `disk_used_pct`, `pressure_level`) — `modules.common.runtime_target.read_hardware_pressure()` + `shutil.disk_usage`

## Mimari

- Giriş noktası: `xTelemetryService.py`
- **Registry & Metrics**: `services/metrics.py` → `Registry`, `Counter`, `Gauge`, `Summary`, `SystemSnapshot`, `read_system_snapshot()`
- **Router**: `api/router.py` → `/telemetry/healthz`, `/telemetry/metrics`, `/telemetry/snapshot`, `/telemetry/events`
- **Config**: `config_loader.py` → `modules.common.config_loader.load_module_config` + `modules.common.bind_host.apply_bind_host(..., "TELEMETRY_HOST")`

Gateway `_IMPORT_MODULES` ile `include.telemetry=true` olduğunda mount edilir (`bootstrap_ops.py`).

## API (Gateway altında `/telemetry/*`)

- `GET /telemetry/healthz` — `{ "ok": true, "exporter": "builtin" }`
- `GET /telemetry/metrics` — Prometheus scrape formatı (`exporter.type: none` ise HTTP `503`)
- `GET /telemetry/snapshot` — `{ "ok": true, "exporter": "...", "host": {...}, "gauges": {...}, "counters": {...}, "summaries": {...} }`
- `POST /telemetry/events` — `{ "type": "wakeword", "latency_ms": 18.4 }` → `events_total`, `event_<type>_total` (64 sınırından sonra `event_other_total`) ve opsiyonel gecikme `Summary` metriğini günceller

## Konfigürasyon

`modules/system_control/telemetry/config/config.yml`:
```yaml
server:
  host: 0.0.0.0
  port: 8097
exporter:
  type: builtin  # builtin|none
```

Env override: `TELEMETRY_HOST` (bind host override).

## İlişkiler

- Harici izleme: Prometheus/Grafana scrape hedefi (`GET /telemetry/metrics`)
- `runtime_console` / TUI / Dashboard: JSON özet sorgusu (`GET /telemetry/snapshot`)
- Otonom karar üretmez; **gözlemlenebilirlik katmanıdır**

## Bilinen Sorunlar & Çözümler

1. **Pushgateway Yok** — Batch job'lar için Prometheus Pushgateway push desteği mevcut değil.
2. ~~**Registry Kilitsiz & Olay Kardinalitesi Sınırsız**~~ ✅ ÇÖZÜLDÜ — `Registry` tüm okuma/yazma/render işlemlerinde `threading.RLock` kullanır; `record_event()` en fazla 64 benzersiz `event_*_total` sayacı oluşturur ve fazlasını `event_other_total` altında toplar.
3. ~~**Atıl `exporter` Ayarı & Yalnızca CPU Snapshot**~~ ✅ ÇÖZÜLDÜ — `exporter.type: none` kontrolü aktif edildi; `read_system_snapshot()` RAM (`mem_available_mb`), disk (`disk_free_gb`, `disk_used_pct`) ve termal basınç seviyesini (`pressure_level`) raporlar; gecikme özeti için `Summary` + `GET /telemetry/snapshot` eklendi.