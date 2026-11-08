# Telemetry Modülü Mimarisi

Telemetry modülü (`modules/system_control/telemetry`), çalışma zamanı olay sayaçlarını, kayan pencereli gecikme özetlerini (`Summary`) ve Raspberry Pi 5 host durumunu (CPU sıcaklık, load, boş RAM, disk kullanımı) thread-safe `Registry` üzerinde toplayıp Prometheus (`/telemetry/metrics`) ve JSON (`/telemetry/snapshot`) olarak sunan gözlemlenebilirlik servisidir.

## İş Akışı ve Karar Mekanizmaları (Flowchart)

```mermaid
flowchart TD
    EVT_IN["POST /telemetry/events (type, latency_ms?)"] --> LOCK_IN["Registry RLock"]
    LOCK_IN --> CAP{"Benzersiz olay tipi < 64 veya kayitli mi?"}
    CAP -- "Evet" --> INC_TYPE["event_<type>_total +1 (+ opsiyonel Summary)"]
    CAP -- "Hayir (OOM Korumasi)" --> INC_OTHER["event_other_total +1"]

    EXP_REQ["GET /telemetry/metrics"] --> CHK_EXP{"exporter.type == none?"}
    CHK_EXP -- "Evet" --> RET_503["HTTP 503 exporter disabled"]
    CHK_EXP -- "Hayir (builtin)" --> HOST_SNAP["read_system_snapshot (CPU, RAM, Disk)"]
    HOST_SNAP --> FMT_PROM["Prometheus Gauge/Counter/Summary cikti (200)"]

    SNAP_REQ["GET /telemetry/snapshot"] --> HOST_JSON["read_system_snapshot + Registry.snapshot()"]
    HOST_JSON --> RET_JSON["JSON host + gauges/counters/summaries"]
```

## İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    RuntimeTarget ||--|| TelemetryMetrics : provides_pressure_snapshot
    ModulesOrGateway ||--o{ TelemetryRouter : posts_events
    PrometheusServer ||--|| TelemetryRouter : scrapes_metrics
    RuntimeConsole ||--|| TelemetryRouter : reads_json_snapshot

    Registry {
        RLock lock
        dict counters
        dict gauges
        dict summaries
        int max_event_types
    }
```

## Detaylı Karar Mantığı

1. **Kardinalite ve Bellek Koruması (OOM Guard)**
   - Sınırsız farklı `ev["type"]` değeri RPi 5 belleğini doldurmasın diye `Registry.record_event` en fazla 64 benzersiz olay tipini ayrı sayaç/özet olarak tutar; taşan tüm olaylar `event_other_total` altında toplanır.
2. **Thread Güvenliği (`RLock`) ve Gecikme Özeti (`Summary`)**
   - `Registry` tüm `counter`/`gauge`/`summary` ekleme, `render_prometheus()` ve `snapshot()` kopyalama işlemlerini `threading.RLock` altında yapar; `Summary` ise son 256 örneklik kayan pencerede ek kütüphanesiz `avg`, `p50`, `p95`, `max` hesaplar.
3. **Exporter Modu ve Hata Kaydı**
   - `exporter.type: none` ayarında `/telemetry/metrics` HTTP `503` döner; host ölçümü okumalarındaki istisnalar sessiz yutulmaz, `debug` seviyesinde loglanır.
