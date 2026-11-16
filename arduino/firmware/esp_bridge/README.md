# SentryBOT ESP Bridge Firmware (ESP32)

Bu firmware, Raspberry Pi (veya başka bir üst katman) ile Arduino Mega arasındaki yüksek performanslı taşıma ve kontrol katmanıdır.

## Modern Mimari (RTOS & Modüler)
Bu sürüm, **FreeRTOS** kullanarak eşzamanlı görev yönetimini destekler:
- **UartTask**: Mega'dan gelen NDJSON verilerini arka planda kesintisiz okur.
- **Bridge-Only Tasarım**: ESP32 yalnızca UART köprüsü, heartbeat ve telemetry taşıma görevlerini yürütür.
- **Modüler Yapı**: Kod; `config.h`, `RobotState.h` ve `UartHandler` olarak mantıksal parçalara bölünmüştür.

## Özellikler
- **UART Köprüsü (Mutex + Kuyruk)**: FreeRTOS `uartSendLine` TX mutex ve `QueueHandle_t` yanıt kuyruğu ile `uartTask`, `linkTask` ve HTTP işleyicileri arasında yarış koşullarını önler.
- **Erken Link Keepalive**: UART ve 200ms `hb` görevleri Wi-Fi bağlantısından önce başlar.
- **mDNS & Yerel Konfigürasyon**: Varsayılan mDNS adı `sentrybot-2` (`sentrybot-2.local`, Pi `config.yml` ile uyumlu). Wi-Fi ve `BRIDGE_AUTH_TOKEN` ayarları için `local_config.h.example` kopyalanıp `local_config.h` oluşturulabilir.
- **Gözlem Amaçlı Serial Log**: Bağlantı durumu ve robot verileri seri port üzerinden izlenir.

## Endpointler
- `GET /` : Web kontrol ve önbellekli sensör arayüzü
- `GET /healthz` : gerçek Mega link durumu (`link_alive`), `wifi`, `uptime_ms`, `uart_rx_errors` ve `uart_overflows` sayaçları
- `GET /state` : önbellekteki `g_robotState` telemetri/sensor özeti (Mega UART'ını yormadan)
- `POST /send` : opsiyonel `X-API-Key`/`Bearer` token doğrulamalı, tek-satır JSON fire-and-forget iletimi
- `POST /request` : `?timeout=<sn>` destekli, `hb`/telemetri dışlayan ve `seq` eşleştiren senkron istek ucu

Not: Firmware uyumluluk için hem `HTTP_PORT` (varsayılan 8080) hem de `80` portunu dinleyebilir.

## Kurulum & Gereksinimler
- **Kart**: ESP32 Dev Module
- **Kütüphaneler**: `ArduinoJson`
- **Pin Tanımları**: `config.h` içinden değiştirilebilir (Varsayılan: RX=16, TX=17).

## Donanım Bağlantısı
- ESP32 TX2 (GPIO17) -> Mega RX1 (Pin 19)
- ESP32 RX2 (GPIO16) -> Mega TX1 (Pin 18)
- Baud Hızı: 115200
