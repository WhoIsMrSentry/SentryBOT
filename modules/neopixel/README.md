# Neopixel Module

DryCode uyumlu, hem kütüphane hem servis olarak çalışabilen NeoPixel (WS2812) kontrol modülü. Pi5 üzerinde `pi5neo` ile donanım sürer; donanım yoksa simülatör çalışır.

## Özellikler
- Donanım/simülatör otomatik seçim
- Efektler: rainbow, theater_chase, fill, clear
- ESP tarzı gelişmiş animasyonlar: RAINBOW, RAINBOW_CYCLE, SPINNER, BREATHE, METEOR, FIRE, COMET, WAVE, PULSE, TWINKLE, COLOR_WIPE, RANDOM_BLINK, THEATER_CHASE, SNOW, ALTERNATING, GRADIENT, BOUNCING_BALL, RUNNING_LIGHTS, STACKED_BARS, MULTI_GRADIENT, MULTI_WAVE
- Duygular (emotions) paleti: her duygu için çoklu renk, isimleri ile birlikte
- FastAPI servisi ile HTTP üzerinden kontrol

## Kurulum ve Çalıştırma (Servis)
Python ile:

```python
from modules.neopixel.xNeopixelService import create_app
app = create_app()
```

Uvicorn ile çalıştırma:
```bash
uvicorn modules.neopixel.xNeopixelService:create_app --factory --host 0.0.0.0 --port 8092
```

## API Uç Noktaları

- GET  `/neopixel/healthz`
- POST `/neopixel/clear`
- POST `/neopixel/fill?r=255&g=0&b=0`
- POST `/neopixel/rainbow?wait=0.02&cycles=3`
- POST `/neopixel/theater_chase?r=255&g=0&b=0&wait=0.05&cycles=10`
- POST `/neopixel/effect?name=rainbow|theater_chase|fill|clear`
- POST `/neopixel/emote` body: `{ "text": "joy curiosity", "duration": 0.25 }` veya query `emotions=joy&emotions=fear`
	- Döner: seçilen renk adları ve rgb: `{ chosen: [{emotion, name, rgb}, ...] }`
- POST `/neopixel/emote_named?emotion=joy&name=COLOR_SUNSHINE&duration=0.25`
- POST `/neopixel/animate?name=RAINBOW&emotions=joy&emotions=fear&iterations=2`

### Animasyon İsimleri ve Parametreleri

Tek renk kullananlar (c1):
- SPINNER(color=c1, iterations=1)
- BREATHE(color=c1, iterations=1, step=5, wait=0.02)
- METEOR(color=c1, size=5, decay_ms=50)
- FIRE(color=c1, cycles=1)
- COMET(color=c1, speed_ms=50)
- PULSE(color=c1, step=10, wait=0.05)
- TWINKLE(color=c1, count=5, wait=0.1)
- COLOR_WIPE(color=c1, speed_ms=50)
- RANDOM_BLINK(color=c1 veya None, wait=0.1)
- THEATER_CHASE(color=c1, wait=0.05, cycles=5)
- SNOW(color=c1, flakes=10, wait=0.2)
- GRADIENT(color=c1, cycles=5, wait=0.03)
- BOUNCING_BALL(color=c1, frames=60, wait=0.03)
- RUNNING_LIGHTS(color=c1, loops=2, wait=0.05)
- STACKED_BARS(color=c1 veya None, wait_ms=50)

Tint’li/çoklu renk kullananlar:
- RAINBOW(color=c1 veya None, iterations=1, wait=0.02)
- RAINBOW_CYCLE(color=c1 veya None, iterations=1, wait=0.02)
- WAVE(color=c1 veya None, wait=0.05)
- MULTI_GRADIENT(colors=[c1,c2,...], iterations=5, wait=0.03)
- MULTI_WAVE(colors=[c1,c2,...], iterations=5, wait=0.03)

Notlar:
- API’de `iterations` parametresi genel amaçlıdır; bazı animasyonlar bu değeri kullanır.
- Renkler `emotions` listesinden rastgele seçilir (cache). Birden fazla emotion vererek çoklu renkli animasyonlar çalıştırabilirsiniz.

## Emotions Paleti

- Yol: `modules/neopixel/emotions/` altında her duygu için `*.yml`
- Schema:

```yaml
colors:
	- { name: COLOR_SUNSHINE, r: 255, g: 215, b: 0 }
	- "#FF00FF"
	- [0, 255, 128]
```

- Loader: `modules/neopixel/emotions/loader.py`
	- random_color(emotion): (r,g,b)
	- random_entry(emotion): { name, color }
	- get_by_name(emotion, name)

## Config
`modules/neopixel/config/config.yml` içinde. Ortam değişkenleri: NEO_DEVICE, NEO_NUM_LEDS, NEO_SPEED_KHZ, NEO_ORDER, NEO_HOST, NEO_PORT.

## Kütüphane Kullanımı

```python
from modules.neopixel.services.runner import NeoRunner
from modules.neopixel.services.driver import NeoDriverConfig

runner = NeoRunner(NeoDriverConfig(num_leds=30))

# Basit efekt
runner.rainbow()

# Duygu sırası ile renk gösterimi
runner.emote_sequence(["joy", "fear"], duration=0.2)

# Animasyon, duygulardan renk üretip uygular
runner.animate("ALTERNATING", emotions=["anger", "gratitude"], iterations=10)
```

## Gateway ile Kullanım
Gateway çalışırken NeoPixel API uçları tek portta `/neopixel/*` altında sunulur. `interactions` modülü de gateway’de açıksa, kurallar NeoPixel efektlerini otomatik tetikler; modülü ayrı bir servis olarak çalıştırmaya gerek yoktur.