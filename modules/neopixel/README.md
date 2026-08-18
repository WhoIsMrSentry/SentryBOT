# Neopixel

WS2812/NeoPixel LED kontrol modülüdür. Hem kütüphane hem servis olarak çalışır; duygu paletleri, segment desteği ve preset kütüphanesi sunar.

## Sorumluluklar

- Donanım/simülatör otomatik seçimi (Pi SPI, Arduino, sim)
- Temel efektler ve gelişmiş animasyon ailesi
- Duygu paletleri (`emotions/*.yml`)
- Segment bazlı kontrol (jewel/stick)
- Runtime preset CRUD
- Companion LED yüz/VU/thinking frame render (`companion_leds.py`)

## Mimari

- Giriş noktası: `xNeopixelService.py`
- Runner: `services/runner.py` (`NeoRunner`)
- Sürücü: `services/driver.py`
- Duygu loader: `emotions/loader.py` (`common.emotion_vocab` ile uyumlu)
- Router: `api/router.py`

## API (Gateway altında `/neopixel/*`)

- `GET /neopixel/healthz`
- `POST /neopixel/clear`, `/fill`, `/rainbow`, `/theater_chase`
- `POST /neopixel/effect`, `/animate`, `/emote`, `/emote_named`
- `GET /neopixel/segments`
- `POST /neopixel/segment/clear`
- `GET /neopixel/presets`
- `POST /neopixel/preset/apply`, `/preset/set`
- `GET /neopixel/preset/get`
- `DELETE /neopixel/preset/delete`

## Konfigürasyon

`modules/neopixel/config/config.yml`:
- `hardware.backend`: `auto|pi|arduino|sim`
- `hardware.segments`
- `presets`
- `hardware.num_leds`, SPI ayarları

Env: `NEO_DEVICE`, `NEO_NUM_LEDS`, `NEO_BACKEND`, vb.

## İlişkiler

- `interactions`: kural motoru efekt tetikleme
- `autonomy`: duygu paletleri, scene orchestration
- `expression`: LED modality
- `common.emotion_vocab`: palette/effect eşlemesi
- `arduino_serial`: fiziksel sürüş fallback'i

Robotun duygusal durumunu ışıkla dışa vuran birincil donanım katmanıdır.
