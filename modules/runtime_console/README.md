# Runtime Console Module

SentryBOT için tasarlanmış logo barındırmayan, TUI (Terminal User Interface) veya panel tabanlı kompakt terminal görünüm modülüdür. Sistem durumlarını, logları ve event akışlarını gözlemlemek için kullanılır.

## Özellikler
- **Event Bus:** Modüller arası olayları (event) toplayarak, ekranda veya API üzerinden canlı akış şeklinde sunar.
- **Konsol Filtreleme:** Kamera, VLM sağlık kontrolleri gibi sık tekrar eden arka plan HTTP isteklerini gizleyerek log kalabalığını önler.
- **Çoklu Mod:** Geniş ekran (dashboard) veya dar ekran (compact) çalışma düzenini destekler.

## API Uç Noktaları

Uç noktalar Gateway altında `/runtime_console` prefix'i ile çalışır.

- `GET /runtime_console/healthz`
  Servisin aktif olup olmadığını ve event bus üzerinde birikmiş toplam event sayısını döner.

- `GET /runtime_console/events?limit=20`
  Event bus'ın kuyruğundaki (tail) son olayların (event) JSON listesini döndürür. Arayüzler veya dış izleme araçları bu uç noktayı çağırarak robotta neler olup bittiğini okuyabilir.

## Konfigürasyon (`config/config.yml`)
- `ui_mode`: Arayüzün görüntülenme modunu belirler (`dashboard` vs `compact`).
- `hide_health_checks`: Sürekli tekrar eden `/healthz` veya `/status` pinglerini terminalde gizler (varsayılan: `true`).

Tam teknik loglar (debug ve trace düzeyleri) `logs/sentry.log` dosyasına aktarılmaya devam eder, bu modül sadece canlı izleme deneyimini temizler.
