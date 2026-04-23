# ESP Bridge Firmware (ESP32)

Bu firmware, Pi ile Mega arasındaki yeni taşıma katmanıdır.

## Mimari
- Pi -> ESP32: HTTP (`/send`, `/request`)
- ESP32 -> Mega: UART NDJSON
- Mega: mevcut komut işleme (ekran, lazer, buzzer, stepper, servo, vb.) aynen korunur

## Ağ
- SSID: `SentryBOT`
- Şifre: `SentryBOT`

## UART Bağlantı
- ESP32 TX2 (GPIO17) -> Mega RX1 (pin 19)
- ESP32 RX2 (GPIO16) -> Mega TX1 (pin 18)
- Baud: 115200

## Endpointler
- `GET /healthz`
- `POST /send` -> ACK beklemeden Mega'ya iletir
- `POST /request?timeout=1.2` -> Mega ACK/ERR bekler ve JSON döner

## Not
Bu köprü için `ArduinoJson` kütüphanesi gereklidir.
