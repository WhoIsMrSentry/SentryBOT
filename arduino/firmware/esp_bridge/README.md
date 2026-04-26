# SentryBOT ESP Bridge Firmware (ESP32)

Bu firmware, Raspberry Pi (veya Web Arayüzü) ile Arduino Mega arasındaki yüksek performanslı taşıma ve kontrol katmanıdır.

## Modern Mimari (RTOS & Modüler)
Bu sürüm, **FreeRTOS** kullanarak eşzamanlı görev yönetimini destekler:
- **UartTask**: Mega'dan gelen NDJSON verilerini arka planda kesintisiz okur.
- **WebServerTask**: Web Dashboard ve API isteklerini karşılar.
- **Modüler Yapı**: Kod; `config.h`, `RobotState.h`, `UartHandler` ve `WebServerHandler` olarak mantıksal parçalara bölünmüştür.

## Özellikler
- **mDNS Erişimi**: `http://sentrybot.local` adresinden doğrudan erişim.
- **İnteraktif Dashboard**: Canlı sensör verileri (Mesafe, IMU, Sıcaklıklar) ve RFID takibi.
- **Sanal Kumanda**: Robotun fiziksel LCD menülerinde gezinmek için entegre IR kumanda arayüzü.
- **Gelişmiş Kontrol**: Lazer ve Buzzer (Ses Paleti) için doğrudan kontrol butonları.

## Endpointler
- `GET /` -> İnteraktif Web Dashboard
- `GET /api/state` -> Tüm sensör verilerini içeren JSON objesi
- `POST /send` -> JSON komutlarını Mega'ya iletir
- `POST /raw` -> Ham metin komutlarını iletir (Kumanda tuşları vb.)
- `GET /healthz` -> Sistem sağlık kontrolü

## Kurulum & Gereksinimler
- **Kart**: ESP32 Dev Module
- **Kütüphaneler**: `ArduinoJson`, `WebServer`, `ESPmDNS`
- **Pin Tanımları**: `config.h` içinden değiştirilebilir (Varsayılan: RX=16, TX=17).

## Donanım Bağlantısı
- ESP32 TX2 (GPIO17) -> Mega RX1 (Pin 19)
- ESP32 RX2 (GPIO16) -> Mega TX1 (Pin 18)
- Baud Hızı: 115200
