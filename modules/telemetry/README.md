# Telemetry Module

Hafif metrik ve olay yayın modülü. `/telemetry/metrics` Prometheus uyumlu metin çıktısı sağlar.

## API
- GET `/telemetry/healthz`
- GET `/telemetry/metrics`
- POST `/telemetry/events` `{ type: string, ... }`
