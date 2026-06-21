# Skill: diagnostics

## Ana bileşen
- Sınıf: `None` in `modules/diagnostics/xDiagnosticsService.py`
- Mission: Sistem sağlık testi (Arduino, kamera, Ollama)

## API özeti
- `GET /healthz` → `healthz()` → —
- `POST /run` → `run()` → —
- `GET /report` → `report()` → —

## Dış ilişkiler (neden)
- → [[arduino_serial]] (http): Arduino bağlantı sağlık testi yapar.
- → [[arduino_serial]] (registry): Arduino bağlantı sağlık testi yapar.
- → [[camera]] (http): Kamera erişim ve stream testi yapar.
- → [[camera]] (registry): Kamera erişim ve stream testi yapar.
- → [[neopixel]] (http): `diagnostics` HTTP ile `neopixel` modülüne erişir: LED animasyon veya duygu preset uygular.
- → [[ollama]] (registry): Ollama servis erişilebilirlik testi yapar.
- → [[speak]] (http): `diagnostics` HTTP ile `speak` modülüne erişir: TTS servisinin hazır olup olmadığını kontrol eder.
- → [[speech]] (http): `diagnostics` HTTP ile `speech` modülüne erişir: Ses tanıma (ASR) pipeline'ına istek gönderir.
- → [[wakeword]] (http): `diagnostics` gateway veya doğrudan HTTP ile `wakeword` API'sini çağırır (calls path `/wakeword/status`).

## Gelen ilişkiler (neden)
- ← [[gateway]] (import): `gateway` kod içinde `diagnostics` modülünü import eder (`api`) — Sistem sağlık testi (Arduino, kamera, Ollama).
- ← [[gateway]] (import): `gateway` kod içinde `diagnostics` modülünü import eder (`config_loader`) — Sistem sağlık testi (Arduino, kamera, Ollama).
- ← [[scheduler]] (http): `scheduler` → `diagnostics`: Sistem sağlık kontrolü çalıştırır.

## Tam bilgi
`.sentrybot/obsidian/modules/diagnostics.md` (11 dosya, 388 satır)
