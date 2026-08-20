# LogWrapper Modülü Mimarisi

LogWrapper modülü (`modules/logwrapper`), sistem genelindeki standart `logger` (logging) akışlarını toplayarak, hem konsola renkli bastıran (rich tabanlı) hem de WebSocket üzerinden web paneline anlık olarak (canlı log streaming) ileten merkezi log yakalayıcısıdır.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

```mermaid
flowchart TD
    %% Log Yakalama Akışı
    G_LOG("Herhangi Bir Modülde<br>logger.error/info") --> CATCH_HND("WebSocketLogHandler<br>Yakalar (Intercept)")
    
    CATCH_HND --> FMT_JSON("Zaman, Modül Adı, Renk<br>Bilgilerini JSON Yap")
    
    FMT_JSON --> WS_BCAST("Tüm Aktif WebSocket<br>İstemcilerine Yolla")
    
    %% WS İstekleri
    FRONTEND("Web Arayüzü<br>(Admin Panel)") --> REQ_WS("WS /logs/stream")
    REQ_WS --> ADD_CLIENT("İstemciyi Aktif Listeye<br>(clients_set) Ekle")
    ADD_CLIENT --> WAIT_LOGS("Log Bekleme Döngüsü")
    WS_BCAST --> WAIT_LOGS
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    LogWrapper ||--o{ AllModules : intercepts_stdout
    LogWrapper ||--o{ WebUsers : websockets

    LogWrapper {
        string stream_name
        int buffer_size
    }
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **İstemci (Client) Yönetimi**
   - Web üzerinde log izleyen ekran kapatılırsa (veya tarayıcı çökerse), WebSocket bağlantısı kopar.
   - **`try / except WebSocketDisconnect`**: Bu durumda sistemdeki aktif bağlantı kümesinden (`clients.remove(ws)`) istemciyi derhal siler. Bu işlem yapılmazsa, bir sonraki `logger.info("Merhaba")` çağrıldığında sistem ölü bir sokete veri yazmaya çalışıp çöker.
2. **Buffer (Kuyruk) Mekanizması**
   - **`if`** aktif hiçbir WebSocket bağlantısı yoksa loglar uzaya gitmez, küçük bir "Son N log" değişken dizisinde tutulmaya devam edebilir (Eski logları paneli açar açmaz görebilmek için geçmiş log belleği (History Buffer) kullanımı).
