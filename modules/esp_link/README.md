# ESP Link Module

Raspberry Pi tarafında, WiFi üzerinden bağlı olan bir ESP32 "köprü (bridge)" cihazı ile haberleşmeyi sağlayan proxy modülüdür. Bu modül sayesinde robot, ESP32 üzerinden çalışan ek donanımlara veya sensörlere doğrudan erişebilir.

## Özellikler
- **HTTP Köprüsü:** ESP cihazına doğrudan IP/Port vererek gitmek yerine, Gateway içerisinde `/esp` altında standart bir API sunar.
- **İki Yönlü İletişim:** İster tek yönlü veri gönderimi (fire-and-forget), ister yanıt beklemeli (request-response) iletişim kurulabilir.

## API Uç Noktaları

Tüm uç noktalar varsayılan olarak Gateway altında `/esp` prefix'i ile sunulur.

- `GET /esp/healthz`
  ESP32 cihazına bir sağlık (ping) isteği atar. Cihaz ağda ve yanıt veriyorsa `ok: true` döner.

- `POST /esp/send`
  ESP32'ye JSON tabanlı asenkron veri veya komut gönderir. Yanıt beklenmeden istek tamamlanır (fire-and-forget komutları için idealdir).
  **Gövde (JSON):** ESP32 cihazının beklediği herhangi bir JSON yapısı.

- `POST /esp/request?timeout=1.0`
  ESP32'den bilgi talep eden senkron (cevap beklemeli) uç noktadır.
  **Gövde (JSON):** Talep komutu (örneğin `{ "cmd": "get_sensor" }`).
  **Dönen Yanıt:** ESP32'den dönen raw JSON objesi.

## Konfigürasyon (`config/config.yml`)
- `base_url`: ESP bridge cihazının HTTP adresi (ör: `http://192.168.1.100` veya DNS adı).
- `paths`: ESP cihazının içerideki rotaları (örneğin `/health`, `/send`, `/request`).
- `timeouts`: İletişim zaman aşımları (`connect_s`, `io_s`).
