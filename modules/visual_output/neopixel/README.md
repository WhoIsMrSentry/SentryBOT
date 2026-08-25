# Visual Output - NeoPixel

WS2812/NeoPixel LED kontrol modülüdür. Hem kütüphane hem servis olarak çalışır; duygu paletleri, segment desteği ve preset kütüphanesi sunar.

## Sorumluluklar

- Donanım/simülatör otomatik seçimi (Pi SPI, Arduino, sim)
- Temel efektler ve gelişmiş animasyon ailesi
- Duygu paletleri (`emotions/*.yml`) - `common.emotion_vocab` ile uyumlu
- Segment bazlı kontrol (jewel/stick/ring)
- Runtime preset CRUD (YAML persist + version)
- Companion LED yüz/VU/thinking frame render (`services/companion_leds.py`)

## Mimari (Güncel: 2026-08-20)

- Giriş noktası: `xNeopixelService.py`
- **Runner**: `services/runner.py` → `NeoRunner(RunnerPresetsMixin, RunnerCompanionMixin)` (ana state machine)
- **Driver**: `services/driver.py` → `NeoDriver`, `NeoDriverConfig` (hardware abstraction)
- **Companion**: `services/companion_leds.py` → `CompanionLedController(CompanionLedRenderMixin)` (face frames, thinking, wake spin)
- **Segments**: `services/runner.py` içinde segment logic
- **Presets**: `services/runner_presets.py` → `RunnerPresetsMixin` (preset CRUD + YAML persist)
- **Router**: `api/router.py`

## API (Gateway altında `/neopixel/*`)

### Core
- `GET /neopixel/healthz`
- `POST /neopixel/clear`, `/fill`, `/rainbow`, `/theater_chase`
- `POST /neopixel/effect`, `/animate`, `/emote`, `/emote_named`

### Segments
- `GET /neopixel/segments`
- `POST /neopixel/segment/clear` - segment uçlarından yalnız bu var
- Segment fill ayrı uçtan değil: `POST /neopixel/fill?segment=<name>` parametresiyle yapılır (`/animate` da `segment` destekler)

### Presets (Runtime CRUD)
- `GET /neopixel/presets`
- `POST /neopixel/preset/apply`, `/preset/set`
- `GET /neopixel/preset/get`
- `DELETE /neopixel/preset/delete`

### Companion Modes (Internal)
- `POST /neopixel/companion/mode` - `thinking`, `wake`, `listening`, `speaking`, `idle`, `face_frame`
- `GET /neopixel/companion/semantics` - semantik companion kataloğu
- `POST /neopixel/companion/semantic` - semantik companion komutu uygula
- `GET /neopixel/companion/status` - companion durumu

### Prompt
- `POST /neopixel/prompt`

### Animations List
- `GET /neopixel/animations` - curated list (use `?show_all=true` for all)
- `GET /neopixel/emotions` - emotion names list

## Konfigürasyon

`modules/visual_output/neopixel/config/config.yml`:
- `hardware.backend`: `auto|pi|arduino|sim`
- `hardware.segments`: `[{"name": "jewel", "start": 0, "count": 7}, {"name": "stick_left", "start": 7, "count": 8}, {"name": "stick_right", "start": 15, "count": 8}]` (anahtar `length` değil `count`)
- `hardware.num_leds`, `speed_khz`, `ws2812_spi_khz`, `order` (GRB)
- `presets`: named preset definitions
- `companion`: companion mode configs

Env override: `NEO_DEVICE`, `NEO_NUM_LEDS`, `NEO_BACKEND`, `NEO_SPEED_KHZ`

## İlişkiler (Güncel Modül Yolları)

- `expression/interactions` → Kural motoru efekt tetikleme (event → effect)
- `autonomy` → Duygu paletleri, scene orchestration (mood → LED)
- `expression` → LED modality (`ExpressionArbiter` lease ile)
- `common.emotion_vocab` → Palette/effect eşlemesi (canonical emotion names)
- `arduino_serial` → Fiziksel sürüş fallback'i (Arduino firmware NeoPixel varsa)
- `visual_output/oled_faces` → Face frame koordinasyonu (companion_leds face_frame)

## ExpressionArbiter Lease (ZORUNLU)

Tüm LED kontrolü **ExpressionArbiter** lease'ından geçer:
```python
# Otomatik: /expression/express tool veya event → state → arbiter
arbiter.claim_lights(source="autonomy", priority=80, ttl_s=2.0)

# Companion modes da lease alır:
arbiter.claim_lights(source="companion_thinking", priority=95, ttl_s=0.5)
```

**Öncelik Sırası** (`modules/agent_core/config/config.yml` → `expression_lease.priorities`): `emergency` (100) > `hardware_protection` (90) > `safety_navigation` (80) > `owner_command` (60) > `interactions` (40) > `autonomy` (20); `default`/`ambient_idle`: 10

## Bilinen Sorunlar

1. ~~**NeoRunner Çok Büyük** (615 satır)~~ **Çözüldü** - `runner.py` artık ~322 satır; mixins'lere bölündü (`runner_presets.py`, `runner_companion.py`)
2. **Arduino Bridge** - `arduino_serial` event handler (`neopixel_request`) → `NeoRunner` direct, arbiter lease kontrolü var ama race condition riski
3. **Duplicate Emotion Maps** - `emotions/*.yml` + `common.emotion_vocab` + `companion_leds.py` kendi map'i → **Tek kaynak: `common.emotion_vocab` olmalı**