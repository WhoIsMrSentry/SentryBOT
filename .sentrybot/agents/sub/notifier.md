# Sub-Agent: notifier-specialist

## Uzmanlık
`None` ve `notifier` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/notifier.md`

## Bileşen haritası
- `CommandResult` — modules/notifier/services/command_router.py
- `CommandRouter` — Map Telegram commands to HTTP calls on other modules.
- `QuietHours` — modules/notifier/services/telegram_bot.py
- `TelegramBot` — modules/notifier/services/telegram_bot.py
- `WhatsAppWebSender` — modules/notifier/services/whatsapp_web.py

## Dış bağlantılar (neden)
- [[neopixel]] (http): `notifier` HTTP ile `neopixel` modülüne erişir: LED animasyon veya duygu preset uygular.

## Gelen bağlantılar (neden)
- [[gateway]] (import): `gateway` kod içinde `notifier` modülünü import eder (`config_loader`) — Telegram/Discord bildirim gönderici.
- [[gateway]] (import): `gateway` kod içinde `notifier` modülünü import eder (`api`) — Telegram/Discord bildirim gönderici.
- [[gateway]] (import): `gateway` kod içinde `notifier` modülünü import eder (`services`) — Telegram/Discord bildirim gönderici.
