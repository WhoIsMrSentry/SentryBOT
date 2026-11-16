# Notifier (Bildirim) Modülü Mimarisi

Notifier modülü (`modules/system_control/notifier`), robot uyarılarını öncelik (`normal`/`critical`) ve sessiz saat (`quiet_hours`) kurallarına göre Telegram ve Discord webhook kanallarına dağıtan, ayrıca güvenli Telegram long-polling üzerinden gateway komutlarını yürüten bildirim köprü servisidir.

## İş Akışı ve Karar Mekanizmaları (Flowchart)

```mermaid
flowchart TD
    REQ_SEND["POST /notify/send (text, priority, channels?)"] --> CHK_QH{"quiet_hours aktif ve priority != critical?"}
    CHK_QH -- "Evet" --> SKIP_QH["Durdur: reason=quiet_hours"]
    CHK_QH -- "Hayir" --> CHK_DEB{"Son cooldown_sec icinde ayni mesaj gonderildi mi?"}
    CHK_DEB -- "Evet" --> SKIP_DEB["Durdur: reason=debounced"]
    CHK_DEB -- "Hayir" --> DISPATCH["Secili aktif kanallara dagit (Telegram, Discord)"]

    POLL_UPD["TelegramBot._handle_update"] --> CHK_AUTH{"_is_authorized(user_id)?"}
    CHK_AUTH -- "Hayir" --> DROP_UNAUTH["Reddet + warning log"]
    CHK_AUTH -- "Evet" --> CHK_BOT_QH{"QuietHours.is_quiet_now()?"}
    CHK_BOT_QH -- "Evet" --> DROP_SILENT["Sessizce yoksay (yanit atma)"]
    CHK_BOT_QH -- "Hayir" --> CMD_ROUTE["CommandRouter -> CommandRegistry.handle(...)"]
```

## İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    NotifierRouter ||--o{ TelegramBot : dispatches_and_controls
    NotifierRouter ||--o{ SyncSenders : threadpool_http_post
    TelegramBot ||--|| CommandRouter : routes_bot_commands
    CommandRouter ||--|| GatewayHTTP : calls_with_shared_client
    Diagnostics ||--o{ NotifierRouter : sends_alerts
    Scheduler ||--o{ NotifierRouter : executes_notify_jobs
```

## Detaylı Karar Mantığı

1. **Varsayılan Reddet (`allow_public` + `allowed_user_ids`)**
   - `allowed_user_ids` boşsa `allow_public: true` açıkça ayarlanmadıkça hiçbir Telegram kullanıcısı komut yürütemez; geçersiz env ID girdileri başlangıcı çökertmeden uyarı loguyla atlanır.
2. **Ortak Sessiz Saat ve Flood Koruması**
   - `QuietHours` ve HTTP router aynı `modules.common.time_utils` (`parse_hhmm`, `is_time_in_window`) mantığını kullanır; `/notify/send` `priority="critical"` dışında tüm kanalları susturur ve başarılı gönderimler için `send.cooldown_sec` süresince aynı mesajı debounce eder.
3. **Paylaşımlı İstemci ve Sır Maskeleme**
   - `TelegramBot` tek `httpx.AsyncClient`, `senders.py` ise tek `httpx.Client` paylaşır; `xNotifierService.py` kapanışta ikisini de kapatır ve hata logları `redact_secrets` + token maskelemesiyle temizlenir.
