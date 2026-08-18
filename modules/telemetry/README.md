# Telemetry

SentryBOT'un hafif metrik toplayıcısıdır. In-memory counter/gauge registry tutar ve Prometheus scrape formatında sunar.

## Sorumluluklar

- Olay sayaçları (`POST /events`)
- Prometheus `text/plain; version=0.0.4` metrik çıktısı
- Thread-safe in-memory registry

## Mimari

- Giriş noktası: `xTelemetryService.py`
- Registry: `services/metrics.py` (`Registry`, `Counter`, `Gauge`)
- Router: `api/router.py`

Gateway `_IMPORT_MODULES` ile `include.telemetry=true` olduğunda mount edilir.

## API (Gateway altında `/telemetry/*`)

- `GET /telemetry/healthz`
- `GET /telemetry/metrics` — Prometheus scrape formatı
- `POST /telemetry/events` — `{ "type": "wakeword" }` → `events_total` ve `event_<type>_total` artar

Not: CPU/RAM otomatik toplanmaz; metrikler yalnızca `/events` POST'ları ve manuel gauge set'leriyle oluşur.

## Konfigürasyon

`config/config.yml` — modül-içi minimal ayarlar.

## İlişkiler

- `arduino_serial`: donanım telemetry event'leri (ayrı kanal)
- Harici izleme: Prometheus/Grafana scrape hedefi
- Otonom karar üretmez; gözlemlenebilirlik katmanıdır
