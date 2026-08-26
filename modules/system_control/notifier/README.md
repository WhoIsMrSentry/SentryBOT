# Platform - Notifier

Telegram ve Discord webhook üzerinden dış dünya ile iletişim köprüsüdür. Acil durum uyarıları gönderir; Telegram bot ile gateway komutlarını uzaktan güvenle yürütür.

## Sorumluluklar

- Outbound alert: Telegram, Discord Webhook
- Asenkron Telegram long-polling bot (uzaktan robot kontrolü)
- Quiet hours (sessiz saat) filtresi
- `CommandRouter` ile gateway uzaktan komut yürütme

## Mimari (Güncel: 2026-08-20)

- Giriş noktası: `xNotifierService.py`
- **Telegram Bot**: `services/telegram_bot.py` → `TelegramBot`, `build_telegram_bot()`
- **Senders**: `services/senders.py` → `send_telegram()`, `send_discord()`
- **Komut Proxy**: `services/command_router.py` → `CommandRouter` (plugin registry tabanlı: `modules/common/command_registry.py`)
- **Router**: `api/router.py`
- **Config**: `config_loader.py`

Gateway `_include_notifier` Telegram polling'i startup/shutdown'ta başlatır (`bootstrap_ops.py`).

## API (Gateway altında `/notify/*`)

- `GET /notify/healthz`
- `POST /notify/telegram` — `{ text, chat_id? }`
- `POST /notify/discord` — `{ text }`
- `POST /notify/test` — yapılandırılmış kanallara test mesajı
- `POST /notify/start`, `/notify/stop` — Telegram polling kontrolü

## Telegram Bot Komutları

Gateway `base_url` üzerinden proxy (sadece `allowed_user_ids` listesindeki kullanıcılar):

| Komut | Açıklama | Gateway Endpoint |
|-------|----------|------------------|
| `/status` | Sistem sağlık özeti | `GET /health` |
| `/snap` | Kamera snapshot | `GET /camera/snap` |
| `/pt <pan> <tilt>` | Kafa pan/tilt | `POST /vlm/track` |
| `/pan <angle>` | Kafa pan | `POST /vlm/track` |
| `/tilt <angle>` | Kafa tilt | `POST /vlm/track` |
| `/neofill r g b` | NeoPixel solid fill | `POST /neopixel/fill` |
| `/neoclear` | NeoPixel clear | `POST /neopixel/clear` |
| `/say <metin>` | TTS konuşma | `POST /speak/say` |
| `/help`, `/ping` | Yardım / test | - |

## Konfigürasyon

`modules/system_control/notifier/config/config.yml`:
```yaml
telegram:
  bot_token: ""  # env: SENTRYBOT_TELEGRAM_BOT_TOKEN
  chat_id: ""
  allowed_user_ids: []  # yetkili kullanıcı ID'leri
  polling:
    enabled: false
    interval_sec: 2.5
whatsapp_web:
  enabled: false
  recipient: ""
  send_mode: "instant"   # instant | schedule
  schedule_delay_sec: 90
  wait_time_sec: 15
  close_time_sec: 5
  tab_close: false
discord:
  webhook: ""  # env: SENTRYBOT_DISCORD_WEBHOOK
quiet_hours:
  enabled: false
  start: "23:00"
  end: "08:00"
```

Env override: `SENTRYBOT_TELEGRAM_BOT_TOKEN`, `SENTRYBOT_DISCORD_WEBHOOK`

## İlişkiler (Güncel Modül Yolları)

- `platform/diagnostics` → `notify.enabled: true` + `endpoint: /notify/test` (failed alert)
- `platform/scheduler` → `kind: notify` job'ları
- `gateway` → `base_url` sağlar (command router proxy için)
- `visual_output/neopixel` → `/neopixel/fill`, `/neopixel/clear`
- `vlm_bridge` → `/vlm/track` (pt/pan/tilt)
- `voice/speak` → `/speak/say`
- `camera` → `/camera/snap`

## Bilinen Sorunlar

1. **Telegram Bot + Command Router Tek Dosya** - `telegram_bot.py` 221 satır, polling + command handling + webhook hepsi bir arada. Ayrılmalı: `bot.py`, `polling.py`, `commands/`.
2. **Quiet Hours Sadece Telegram** - Discord webhook için quiet hours filtresi yok.
3. **Error Handling Zayıf** - Telegram API hata durumunda (rate limit, network) retry/backoff yok. Mesaj kaybolur.
4. **Allowed Users Config** - `allowed_user_ids` boşsa herkes komut verebilir. Default deny policy olmalı.

## ✅ Çözüldü

- ~~CommandRouter Hardcoded~~ — `services/command_router.py` artık unified plugin registry kullanıyor (`modules/common/command_registry.py`).
- ~~Discord Webhook Sync (`requests.post`)~~ — `services/senders.py` artık `httpx` kullanıyor.