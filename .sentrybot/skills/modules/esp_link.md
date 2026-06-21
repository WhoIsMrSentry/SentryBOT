# Skill: esp_link

## Ana bileşen
- Sınıf: `xEspLinkService` in `modules/esp_link/xEspLinkService.py`
- Mission: ESP32 köprü iletişimi (mDNS web remote)

## API özeti
- `GET /healthz` → `healthz()` → healthz, request, send
- `POST /send` → `send()` → request, send
- `POST /request` → `request()` → request

## Dış ilişkiler (neden)
- → [[config_center]] (import): `esp_link` → `config_center`: config/agent.yaml dosyasından ayar okur.

## Gelen ilişkiler (neden)
- ← [[gateway]] (import): `gateway` kod içinde `esp_link` modülünü import eder (`xEspLinkService`) — ESP32 köprü iletişimi (mDNS web remote).
- ← [[gateway]] (import): `gateway` kod içinde `esp_link` modülünü import eder (`api`) — ESP32 köprü iletişimi (mDNS web remote).

## Tam bilgi
`.sentrybot/obsidian/modules/esp_link.md` (7 dosya, 199 satır)
