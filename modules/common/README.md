# common — Shared Helpers

Dependency-light helpers shared across SentryBOT modules. Importable from any
service without pulling heavy module graphs.

## Canonical Emotion Vocabulary

`emotion_vocab.py` is the **single source of truth** that unifies the three
historically divergent emotion vocabularies:

| Subsystem        | Old vocabulary                         |
|------------------|----------------------------------------|
| autonomy (mood)  | ~6 labels (`joy`, `sadness`, `tired`…) |
| oled_faces       | ~13 event labels (`happy`, `sad`…)     |
| neopixel         | ~23 palette files                      |

Every subsystem now resolves its incoming label to a **canonical** key and
reads shared render hints, so eyes (OLED), LEDs (NeoPixel), ears (PiServo),
head body-language and TTS tone all agree on one emotion.

### Usage

```python
from modules.common.emotion_vocab import get_vocab

vocab = get_vocab()
vocab.canonical("happy")        # -> "joy"
r = vocab.render("happy")       # -> EmotionRender(...)
r.oled                          # -> "happy"   (face bitmap)
r.palette                       # -> "joy"     (neopixel palette file)
r.effect                        # -> "RAINBOW_CYCLE"
r.ears                          # -> "joy"     (piservo pose key)
r.tone                          # -> "joy"     (speak TTS tone)
r.rgb                           # -> (0, 200, 60)
```

### Config

`config/emotions.yml` defines:

- `aliases` — canonical → alias labels
- `render`  — per-canonical render hints (`oled`, `palette`, `effect`, `ears`, `tone`, `rgb`)
- `default_canonical` — fallback when a label is unknown (`neutral`)

To add or retune an emotion, edit the YAML only — no code changes required.
