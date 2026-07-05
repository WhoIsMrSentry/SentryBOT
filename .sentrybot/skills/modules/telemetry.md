# Skill: telemetry

## Ana bileşen
- Sınıf: `None` in `modules/telemetry/xTelemetryService.py`
- Mission: Prometheus formatında metrik toplama

## API özeti
- `GET /healthz` → `healthz()` → —
- `GET /metrics` → `metrics()` → —
- `POST /events` → `events()` → —

## Dış ilişkiler (neden)
- —

## Gelen ilişkiler (neden)
- ← [[arduino_serial]] (http): `arduino_serial` `telemetry` modülünün HTTP API'sine istek atar (exposes/routes to `/telemetry/start`).
- ← [[arduino_serial]] (http): `arduino_serial` `telemetry` modülünün HTTP API'sine istek atar (exposes/routes to `/telemetry/stop`).
- ← [[gateway]] (import): `gateway` kod içinde `telemetry` modülünü import eder (`api`) — Prometheus formatında metrik toplama.
- ← [[gateway]] (import): `gateway` kod içinde `telemetry` modülünü import eder (`config_loader`) — Prometheus formatında metrik toplama.

## Tam bilgi
`.sentrybot/obsidian/modules/telemetry.md` (11 dosya, 190 satır)
