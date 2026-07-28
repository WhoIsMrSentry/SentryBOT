# Telemetry Module

SentryBOT'un iç sistemlerinden gelen metrikleri toplayan ve bu verileri dış izleme sistemlerine (Prometheus, Grafana) sunan telemetri ve olay (event) toplayıcısıdır.

## Özellikler
- **Prometheus Entegrasyonu:** Standart Prometheus `text/plain; version=0.0.4` formatında metrik çıktıları üretir.
- **Olay Sayaçları:** Sistemde fırlatılan farklı tipteki olayların (event) sayılarını takip ederek istatistik tutar.

## API Uç Noktaları

Uç noktalar Gateway altında `/telemetry` prefix'i ile çalışır.

- `GET /telemetry/healthz`
  Servis sağlık kontrolü.
  
- `GET /telemetry/metrics`
  Tüm toplanmış metrikleri (CPU/RAM kullanımları, özel olay sayaçları vb.) Prometheus'un doğrudan kazıyabileceği (scrape) formata dönüştürerek sunar.

- `POST /telemetry/events`
  Sistemde yeni bir olay gerçekleştiğinde (örneğin wakeword tetiklenmesi, hareket algılanması) sayacı artırmak için çağrılır.
  **Gövde (JSON):** `{ "type": "event_adi", ... }`. Gönderilen type'a göre `event_<type>_total` metrik sayacı 1 artırılır, ayrıca genel `events_total` sayacı artar.

## Konfigürasyon
Metriklerin nerede saklanacağı (eğer persistent bir registry kullanılıyorsa) veya hangi öneklerle dışarı aktarılacağı (prefix) ayarlanabilir.
