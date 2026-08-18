# Common

Modüller arasında paylaşılan, hafif yardımcı kütüphaneler modülüdür. Ağır modül grafiklerini import etmeden ortak davranış sağlar.

## Sorumluluklar

- Kanonik duygu sözlüğü (`emotion_vocab.py`)
- Latency trace deposu (`latency_trace.py`)
- HTTP istemci yardımcıları (`http_client.py`)
- Vision/camera kullanılabilirlik kontrolleri (`vision_availability.py`)
- Model asset doğruluk raporu (`model_asset_truth.py`)
- Runtime hedef tespiti (`runtime_target.py`)
- Sistem prompt yardımcıları (`system_prompts.py`)
- Genel config yardımcıları (`config.py`)

## Duygu Sözlüğü

`emotion_vocab.py`, OLED, NeoPixel, PiServo kulakları, TTS tonu ve agent tool katmanı arasında tek duygu taksonomisi sağlar.

Graph'ta `get_vocab()` 20+ çağrıcıya sahiptir; `autonomy`, `agent_core`, `expression`, `neopixel`, `piservo` gibi modüller bu sözlüğü kullanır.

```python
from modules.common.emotion_vocab import get_vocab

vocab = get_vocab()
vocab.canonical("happy")   # -> "joy"
render = vocab.render("happy")
render.oled, render.palette, render.tone, render.rgb
```

Konfigürasyon: `config/emotions.yml`

## Diğer Yardımcılar

- `latency_trace`: `speak`, `agent_core` gibi modüllerde uçtan uca gecikme izleri
- `http_client`: async/sync HTTP wrapper
- `vision_availability`: kamera/VLM girdisinin gerçekten kullanılabilir olup olmadığını kontrol
- `runtime_target`: Pi/PC hedef ortamını tespit etme

## İlişkiler

`common` bir servis değil, paylaşılan kütüphane katmanıdır. Özellikle otonom ifade senkronizasyonu (`emotion_vocab`) ve performans gözlemi (`latency_trace`) açısından kritiktir.
