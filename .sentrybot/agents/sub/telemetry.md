# Sub-Agent: telemetry-specialist

## Uzmanlık
`None` ve `telemetry` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/telemetry.md`

## Bileşen haritası
- `Counter` — modules/telemetry/services/metrics.py
- `Gauge` — modules/telemetry/services/metrics.py
- `Registry` — modules/telemetry/services/metrics.py

## Dış bağlantılar (neden)
- —

## Gelen bağlantılar (neden)
- [[arduino_serial]] (http): `arduino_serial` `telemetry` modülünün HTTP API'sine istek atar (exposes/routes to `/telemetry/start`).
- [[arduino_serial]] (http): `arduino_serial` `telemetry` modülünün HTTP API'sine istek atar (exposes/routes to `/telemetry/stop`).
- [[gateway]] (import): `gateway` kod içinde `telemetry` modülünü import eder (`api`) — Prometheus formatında metrik toplama.
- [[gateway]] (import): `gateway` kod içinde `telemetry` modülünü import eder (`config_loader`) — Prometheus formatında metrik toplama.
