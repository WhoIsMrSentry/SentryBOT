# Platform - Telemetry

SentryBOT'un hafif metrik toplayıcısıdır. In-memory counter/gauge registry tutar ve Prometheus scrape formatında sunar.

## Sorumluluklar

- Olay sayaçları (`POST /events`)
- Prometheus `text/plain; version=0.0.4` metrik çıktısı
- Thread-safe in-memory registry
- Host gauges (CPU sıcaklığı, 1dk load average) — lokal `read_system_snapshot()` (`services/metrics.py`)

## Mimari (Güncel: 2026-08-20)

- Giriş noktası: `xTelemetryService.py`
- **Registry**: `services/metrics.py` → `Registry`, `Counter`, `Gauge`
- **Router**: `api/router.py`
- **Config**: `config_loader.py`

Gateway `_IMPORT_MODULES` ile `include.telemetry=true` olduğunda mount edilir (`bootstrap_ops.py`).

## API (Gateway altında `/telemetry/*`)

- `GET /telemetry/healthz`
- `GET /telemetry/metrics` — Prometheus scrape formatı (host gauges dahil)
- `POST /telemetry/events` — `{ "type": "wakeword" }` → `events_total` ve `event_<type>_total` artar

## Konfigürasyon

`modules/system_control/telemetry/config/config.yml` — modül-içi minimal ayarlar.

## İlişkiler (Güncel Modül Yolları)

- `hardware` (eski) → `arduino_serial` donanım telemetry event'leri (ayrı kanal)
- Harici izleme: Prometheus/Grafana scrape hedefi
- `platform/scheduler` → periyodik metrik job'ları
- Otonom karar üretmez; **gözlemlenebilirlik katmanıdır**

## Bilinen Sorunlar

1. **Metrics Registry Basit** - `Counter`/`Gauge` sınıfları minimal, label desteği zayıf. Prometheus client library kullanımı düşünülebilir.
2. ~~**Host Gauges Hardcoded**~~ ✅ ÇÖZÜLDÜ - `hardware.services.system` import'u kaldırıldı; `read_system_snapshot()` artık `telemetry/services/metrics.py` içinde lokal tanımlı.
3. **Pushgateway Yok** - Batch job'lar (scheduler, diagnostics) için Prometheus pushgateway entegrasyonu eksik.