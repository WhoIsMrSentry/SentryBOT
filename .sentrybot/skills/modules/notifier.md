# Skill: notifier

## Ana bileşen
- Sınıf: `None` in `modules/notifier/xNotifierService.py`
- Mission: Telegram/Discord bildirim gönderici

## API özeti
- `GET /healthz` → `healthz()` → —
- `POST /telegram` → `tele()` → —
- `POST /discord` → `disc()` → —
- `POST /test` → `test()` → —
- `POST /whatsapp` → `whatsapp_send()` → —
- `POST /start` → `start_bot()` → —
- `POST /stop` → `stop_bot()` → —

## Dış ilişkiler (neden)
- → [[neopixel]] (http): `notifier` HTTP ile `neopixel` modülüne erişir: LED animasyon veya duygu preset uygular.

## Gelen ilişkiler (neden)
- ← [[gateway]] (import): `gateway` kod içinde `notifier` modülünü import eder (`config_loader`) — Telegram/Discord bildirim gönderici.
- ← [[gateway]] (import): `gateway` kod içinde `notifier` modülünü import eder (`api`) — Telegram/Discord bildirim gönderici.
- ← [[gateway]] (import): `gateway` kod içinde `notifier` modülünü import eder (`services`) — Telegram/Discord bildirim gönderici.

## Tam bilgi
`.sentrybot/obsidian/modules/notifier.md` (14 dosya, 877 satır)
