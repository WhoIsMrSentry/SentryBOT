# ESP Link Module

Bu modül, Pi tarafında ESP32 bridge cihazına HTTP üzerinden erişim sağlar.

## Amaç
- Pi -> ESP -> Mega zincirini tek sorumlulukla yönetmek
- Gateway içinde `/esp/*` gözlem ve proxy uçları sağlamak

## Varsayılan Ağ Bilgisi
- SSID: `SentryBOT`
- Şifre: `SentryBOT`

## Konfigürasyon
Ayarlar `modules/esp_link/config/config.yml` içindedir.

Ana alanlar:
- `base_url`: ESP bridge HTTP adresi
- `paths.health|send|request`: endpoint yolları
- `timeouts.connect_s|io_s`: ağ zaman aşımları
