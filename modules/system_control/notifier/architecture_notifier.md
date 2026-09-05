# Notifier (Bildirim) Modülü Mimarisi

Notifier modülü (`modules/notifier`), robottaki önemli olayları veya hataları sahibinin cep telefonuna (Telegram, Discord, Slack) webhook'lar üzerinden güvenli olarak iten (push notification) köprü servisidir.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

```mermaid
flowchart TD
    %% İstek Gelmesi
    EVT_TRIG("Herhangi Bir Modül:<br>POST /notify/send") --> PARSE_MSG("Parametre: title, message, level")
    
    PARSE_MSG --> CHK_LVL{"Level (Seviye)<br>Ne?"}
    
    CHK_LVL -- "INFO" --> SET_ICON("ℹ️ İkonu Ekle")
    CHK_LVL -- "WARNING" --> SET_ICON_W("⚠️ İkonu Ekle")
    CHK_LVL -- "CRITICAL" --> SET_ICON_C("🚨 İkonu Ekle")
    
    SET_ICON --> CHK_TEL{"Telegram Token<br>Tanımlı mı?"}
    SET_ICON_W --> CHK_TEL
    SET_ICON_C --> CHK_TEL
    
    %% API Gönderimi
    CHK_TEL -- "Evet" --> REQ_TEL("Telegram API'ye Req At<br>(SendMessage)")
    CHK_TEL -- "Hayır" --> CHK_DIS{"Discord Webhook<br>Var mı?"}
    
    REQ_TEL --> CHK_DIS
    
    CHK_DIS -- "Evet" --> REQ_DIS("Discord Webhook'a Req At")
    CHK_DIS -- "Hayır" --> FINISH_NOT("İşlem Bitti")
    REQ_DIS --> FINISH_NOT
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    NotifierService ||--o{ ThirdPartyApis : http_post
    Diagnostics ||--o{ NotifierService : triggers_critical
    Interactions ||--o{ NotifierService : triggers_info

    NotifierService {
        string telegram_token
        string discord_webhook
    }
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **Ağ Çökmesi Koruması**
   - Robot internetsiz bir alana girdiğinde (örneğin fuar alanı), Telegram bildirimleri patlayacaktır.
   - Bu modül içindeki tüm HTTP POST işlemleri **`try / except requests.exceptions.RequestException`** bloğu ile sarmalanır. Ağ yanıt vermezse (`Timeout`), fonksiyon uygulamayı kitlemeden `"Bildirim Gönderilemedi"` iç logunu (logger.error) basıp çıkar.
2. **Kuyruklama ve Taşkın (Flood) Önleme**
   - Saniyede 100 kere `CRITICAL` hatası çıkarsa robota ait Telegram API adresi spam sebepli banlanacaktır.
   - Bildirimler gönderilirken, son 10 saniye içinde **`if`** "Aynı Bildirim Gönderildiyse" o bildirimi engeller (Rate Limiting).
