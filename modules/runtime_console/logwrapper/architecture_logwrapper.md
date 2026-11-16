# LogWrapper Modülü Mimarisi

LogWrapper modülü (`modules/runtime_console/logwrapper`), sistem genelindeki standart `logging` akışlarını toplayarak `logs/sentry.log`, ayrı seviye/TUI dosyalarına (`warnings.log`, `errors.log`, yalnızca `runtime_console` için `tui.log`), terminal `RuntimeConsoleLogHandler` panosuna ve `InMemoryLogHandler` bellek ring-buffer'ına güvenli biçimde aktaran merkezi günlük katmanıdır.

## 🏗️ İş Akışı ve Veri Akışı (Flowchart)

```mermaid
flowchart TD
    G_LOG["Tüm Modüller<br>(logging.getLogger)"] --> FILTER["EndpointFilter &<br>DEFAULT_HIDDEN_PATHS"]
    FILTER --> MEM["InMemoryLogHandler<br>(self.lock korumalı ring buffer)"]
    FILTER --> FMT["build_formatter<br>(human veya json.dumps)"]
    FILTER --> ROUTE{"separate_files.enabled?"}
    ROUTE -- "true & runtime_console" --> F_TUI["logs/tui.log (propagate=False)"]
    ROUTE -- "root handlers" --> F_MAIN["logs/sentry.log + warnings.log + errors.log"]
    MEM --> REST_API["REST API (GET /logs/, POST /logs/level)"]
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
