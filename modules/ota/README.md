# OTA

Arduino (avrdude) ve ESP32 (HTTP OTA) firmware yükleme servisidir. Derleme artefaktlarını tarar, SHA256 ile versiyonlar ve opsiyonel güvenlik doğrulaması uygular.

## Sorumluluklar

- `watch_dir` içinde `.hex` / `.bin` artefakt tarama
- Aynı isim+hash tekrar yüklemeyi atlama
- Arduino: `avrdude` ile flash
- ESP32: HTTP POST `/update` (ArduinoOTA uyumlu)
- Allowlist ve HMAC-SHA256 imza doğrulama (opsiyonel)

## Mimari

- Giriş noktası: `xOTAService.py`
- Uploaders: `services/uploader.py`
  - `AvrDudeUploader` — Arduino ATmega
  - `EspOtaUploader` — ESP32 HTTP OTA
  - `OTAService` — birleşik facade
- Router: `api/router.py`

Gateway `_IMPORT_MODULES` ile `include.ota=true` olduğunda mount edilir.

## API (Gateway altında `/ota/*`)

- `GET /ota/healthz`
- `POST /ota/scan_once?target=arduino|esp` — watch_dir tara ve yükle
- `POST /ota/upload?path=&signature=&target=arduino|esp` — manuel yükleme
- `GET /ota/versions` — `{ arduino: {items}, esp: {items} }`
- `POST /ota/versions/clear?target=all|arduino|esp`

## Konfigürasyon

`config/config.yml`:
```yaml
ota:
  watch_dir: arduino/firmware/xMain/build
  artifact_glob: "*.hex"
  board: { mcu, programmer, port, baud }
  avrdude: { bin, config, extra_flags }
  version_db: modules/ota/config/versions.json
  scan_on_start: true
  security:
    enable_allowlist: false
    enable_signature: false
esp_ota:
  base_url: "http://sentrybot-2.local"
  port: 80
  watch_dir: arduino/firmware/esp_bridge/build
  artifact_glob: "*.bin"
```

## İlişkiler

- `arduino_serial`: yükleme sonrası firmware davranışı
- `esp_link`: ESP cihaz iletişimi
- `mutagen`: geliştirme sırasında kod senkronu

Otonomlukta runtime karar üretmez; bakım/deployment aracıdır.
