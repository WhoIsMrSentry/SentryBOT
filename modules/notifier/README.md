# Notifier

Telegram, Discord ve WhatsApp Web üzerinden dış dünya ile iletişim köprüsüdür. Uyarı gönderir; Telegram bot ile gateway komutlarını uzaktan proxy eder.

## Sorumluluklar

- Outbound alert: Telegram, Discord, WhatsApp Web
- Telegram long-polling bot (opsiyonel)
- Quiet hours (sessiz saat) filtresi
- `CommandRouter` ile gateway remote control

## Mimari

- Giriş noktası: `xNotifierService.py`
- Telegram: `services/telegram_bot.py` (`TelegramBot`, `build_telegram_bot`)
- WhatsApp: `services/whatsapp_web.py` (`WhatsAppWebSender`)
- Senders: `services/senders.py` (telegram/discord webhook)
- Komut proxy: `services/command_router.py` (`CommandRouter`)
- Router: `api/router.py`

Gateway `_include_notifier` Telegram polling'i startup/shutdown'ta başlatır. Not: gateway mount'unda WhatsApp sender router'a geçirilmez; tam WhatsApp desteği için standalone servis gerekir.

## API (Gateway altında `/notify/*`)

- `GET /notify/healthz`
- `POST /notify/telegram` — `{ text, chat_id? }`
- `POST /notify/discord` — `{ text }`
- `POST /notify/whatsapp` — `{ text, to?, delay_sec? }` (standalone serviste aktif)
- `POST /notify/test` — tüm kanallara test mesajı
- `POST /notify/start`, `/notify/stop` — Telegram polling kontrolü

## Telegram Bot Komutları

Gateway `base_url` üzerinden proxy:
- `/status` — `/health` aggregate
- `/snap` — kamera snapshot (fotoğraf)
- `/pt <pan> <tilt>`, `/pan`, `/tilt` — `/vlm/track`
- `/neofill r g b`, `/neoclear` — NeoPixel
- `/say <metin>` — `/speak/say`
- `/help`, `/ping`

`allowed_user_ids` boş değilse sadece izinli kullanıcılar etkileşebilir.

## Konfigürasyon

`config/config.yml`:
```yaml
telegram:
  bot_token: ""
  chat_id: ""
  polling: { enabled: false, interval_sec: 2.5 }
whatsapp_web:
  enabled: true
  recipient: "+905..."
  send_mode: instant   # instant | schedule
discord:
  webhook: ""
quiet_hours:
  enabled: false
  start: "23:00"
  end: "08:00"
gateway:
  base_url: "http://127.0.0.1:8080"
```

WhatsApp için `pywhatkit` gerekir; tarayıcıda WhatsApp Web oturumu açık olmalıdır.

## İlişkiler

- `autonomy`: `ServiceClient` notifier start/stop URL'leri
- `camera`, `speak`, `neopixel`, `vlm_bridge`: Telegram komut hedefleri
- Otonomlukta sahip/operatör uzaktan müdahale kanalıdır
