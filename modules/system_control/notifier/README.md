# Platform - Notifier

Telegram ve Discord webhook üzerinden dış dünya ile iletişim köprüsüdür. Öncelikli uyarıları tüm aktif kanallara dağıtır; Telegram bot ile gateway komutlarını uzaktan güvenle yürütür.

## Sorumluluklar

- Outbound alert: Telegram (`bot.send` / `send_telegram`) ve Discord Webhook (`send_discord`)
- Öncelik + anti-flood dağıtımı (`POST /notify/send`: `normal`/`critical`, debounce cooldown)
- Asenkron Telegram long-polling bot (uzaktan robot kontrolü, varsayılan reddet / default-deny)
- Ortak quiet hours (sessiz saat) filtresi (`modules.common.time_utils` tabanlı)
- `CommandRouter` ile gateway uzaktan komut yürütme (`modules.common.command_registry`)

## Mimari

- Giriş noktası: `xNotifierService.py` (kapanışta polling açık olmasa bile `telegram_bot.stop()` ve `close_senders()` temizliği garanti eder)
- **Telegram Bot**: `services/telegram_bot.py` → `TelegramBot`, `QuietHours`, `build_telegram_bot()`
- **Senders**: `services/senders.py` → paylaşımlı `httpx.Client` üzerinden `send_telegram()`, `send_discord()`, `close_senders()`
- **Komut Proxy**: `services/command_router.py` → `CommandRouter` (`services["_http_client"]` enjeksiyonu ile `CommandRegistry.handle(text, user_id=..., chat_id=...)` ve tek-istek fotoğraf yakalama)
- **Router**: `api/router.py`
- **Config**: `config_loader.py` (`load_dotenv`, `load_module_config`, `apply_bind_host(..., "NOTIFIER_HOST")`)

Gateway `_include_notifier` Telegram polling'i startup/shutdown'ta başlatır (`bootstrap_ops.py`).

## API (Gateway altında `/notify/*`)

- `GET /notify/healthz`
- `POST /notify/send` — `{ text|message, priority?: "normal"|"critical", title?, channels?, chat_id? }` (`critical` sessiz saatleri aşar; aynı içerik `send.cooldown_sec` süresi içinde debounced olur)
- `POST /notify/telegram` — `{ text, chat_id? }` (`quiet_hours` uygular)
- `POST /notify/discord` — `{ text }` (`quiet_hours` + `run_in_threadpool` uygular)
- `POST /notify/test` — yapılandırılmış kanallara test mesajı
- `POST /notify/start`, `/notify/stop` — Telegram polling kontrolü

## Telegram Bot Komutları

Gateway `base_url` üzerinden proxy (`allowed_user_ids` listesindeki kullanıcılar veya açık `allow_public: true`):

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
| `/help`, `/ping` | Dinamik yardım / test | - |

## Konfigürasyon

`modules/system_control/notifier/config/config.yml`:
```yaml
server:
  host: 0.0.0.0
  port: 8096
gateway:
  base_url: "http://127.0.0.1:8080"
  timeout_sec: 4.0
telegram:
  bot_token: ""
  chat_id: ""
  allowed_user_ids: []
  allow_public: false
  polling:
    enabled: false
    interval_sec: 2.5
discord:
  webhook: ""
quiet_hours:
  enabled: false
  start: "23:00"
  end: "08:00"
send:
  cooldown_sec: 10.0
```

Env override: `NOTIFIER_BOT_TOKEN`, `NOTIFIER_CHAT_ID`, `NOTIFIER_ALLOWED_USER_IDS`, `NOTIFIER_ALLOW_PUBLIC`, `NOTIFIER_POLLING_ENABLED`, `NOTIFIER_DISCORD_WEBHOOK`, `NOTIFIER_GATEWAY_BASE_URL`, `NOTIFIER_HOST`.

## İlişkiler (Güncel Modül Yolları)

- `platform/diagnostics` → failed alert bildirimleri
- `platform/scheduler` → `kind: notify` job'ları
- `gateway` → `base_url` sağlar (command router proxy için)
- `visual_output/neopixel` → `/neopixel/fill`, `/neopixel/clear`
- `vlm_bridge` → `/vlm/track` (pt/pan/tilt)
- `voice/speak` → `/speak/say`
- `camera` → `/camera/snap`

## Bilinen Sorunlar

1. **Telegram Bot Modülerliği** — Polling, update parsing ve outbound API çağrıları hâlâ `telegram_bot.py` içinde tutuluyor (şimdilik kompakt).
2. **Ağ Retry/Backoff** — Başarısız `send_telegram` / `send_discord` istekleri loglanıyor ancak otomatik yeniden deneme kuyruğu yok.

## Çözüldü

- ~~CommandRouterLegacy Ezmesi & `handle(..., client=...)` Çökmesi~~ — Legacy ezmesi kaldırıldı; `CommandRouter` paylaşımlı istemciyi `services["_http_client"]` üzerinden enjekte edip `CommandRegistry.handle(text, user_id=..., chat_id=...)` imzasıyla çağırır ve tek `/camera/snap` çağrısından fotoğraf baytlarını korur.
- ~~Boş `allowed_user_ids` Açık Erişim Riski~~ — `allowed_user_ids` boşken `allow_public: true` verilmedikçe tüm komutlar reddedilir.
- ~~Discord Quiet Hours & Bloklayıcı Çağrı~~ — `POST /notify/discord` artık `QuietHours` denetler ve `run_in_threadpool` üzerinde paylaşımlı `httpx.Client` kullanır; sessiz saatlerde Telegram mesajlarına rahatsız edici yanıt atılmaz.
- ~~Kapanışta Soket Sızıntısı & Ölü `whatsapp_web` Config~~ — `xNotifierService.py` kapanışta `telegram_bot.stop()` + `close_senders()` her zaman çalıştırır; kullanılmayan `whatsapp_web` config bloğu kaldırıldı.