# SentryBOT ESP Bridge Firmware (ESP32)

Bu firmware, Raspberry Pi (veya başka bir üst katman) ile Arduino Mega arasındaki yüksek performanslı taşıma ve kontrol katmanıdır.

## Modern Mimari (RTOS & Modüler)
Bu sürüm, **FreeRTOS** kullanarak eşzamanlı görev yönetimini destekler:
- **UartTask**: Mega'dan gelen NDJSON verilerini arka planda kesintisiz okur.
- **Bridge-Only Tasarım**: ESP32 yalnızca UART köprüsü, heartbeat ve telemetry taşıma görevlerini yürütür.
- **Modüler Yapı**: Kod; `config.h`, `RobotState.h` ve `UartHandler` olarak mantıksal parçalara bölünmüştür.

## Özellikler
- **UART Köprüsü**: Mega'dan gelen NDJSON satırlarını kesintisiz okur ve yollar.
- **Link Keepalive**: Heartbeat ve telemetry akışını canlı tutar.
- **Gözlem Amaçlı Serial Log**: Bağlantı durumu ve robot verileri seri port üzerinden izlenir.

## Endpointler
- `GET /` : küçük durum sayfası
- `GET /healthz` : köprü sağlık bilgisi
- `POST /send` : fire-and-forget JSON iletimi
- `POST /request` : Mega yanıtını bekleyen istek

Not: Firmware uyumluluk için hem `HTTP_PORT` (varsayılan 8080) hem de `80` portunu dinleyebilir.

## Kurulum & Gereksinimler
- **Kart**: ESP32 Dev Module
- **Kütüphaneler**: `ArduinoJson`
- **Pin Tanımları**: `config.h` içinden değiştirilebilir (Varsayılan: RX=16, TX=17).

## Donanım Bağlantısı
- ESP32 TX2 (GPIO17) -> Mega RX1 (Pin 19)
- ESP32 RX2 (GPIO16) -> Mega TX1 (Pin 18)
- Baud Hızı: 115200
