# ESP Link

Raspberry Pi tarafında WiFi üzerindeki ESP32 köprü cihazına HTTP proxy sağlar. Ek sensör/donanım erişimini gateway altında standart API'ye taşır.

## Sorumluluklar

- ESP32 health ping
- Fire-and-forget komut gönderimi (`/send`)
- Senkron request-response (`/request`)
- Yapılandırılabilir path ve timeout yönetimi

## Mimari

- Giriş noktası: `xEspLinkService.py` (`xEspLinkService`)
- Router: `api/router.py`
- HTTP client: `requests`

Gateway `_include_esp_link` ile mount edilir.

## API (Gateway altında `/esp/*`)

- `GET /esp/healthz` — ESP cihazına ping; `{ ok, resp }`
- `POST /esp/send` — JSON payload, yanıt beklemeden iletir
- `POST /esp/request?timeout=1.0` — JSON payload, ESP yanıtını döner

## Konfigürasyon

`config/config.yml`:
```yaml
base_url: "http://sentrybot-2.local:8080"
paths:
  health: "/healthz"
  send: "/send"
  request: "/request"
timeouts:
  connect_s: 0.4
  io_s: 1.2
```

## İlişkiler

- `arduino_serial`: ana donanım yolu (ESP link alternatif/ek köprü)
- `gateway`: tek port proxy
- Otonomlukta doğrudan karar üretmez; uzak donanım iletişim katmanıdır

Montaj ve edge-device entegrasyonu için kullanılır; kritik servo/stepper yolu `arduino_serial` üzerindedir.
