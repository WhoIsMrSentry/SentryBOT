# Neopixel Event → Animasyon Eşleme (Tam Liste)

> **Birleşik harita (OLED + NeoPixel + servo):** [`docs/robot_expression_map.md`](../../docs/robot_expression_map.md)  
> **CSV:** [`docs/robot_expression_map.csv`](../../docs/robot_expression_map.csv)

Bu belge, repoda bulunan tetikleyici/event kaynaklarının hangi Neopixel animasyon/preset/effect çağrılarını tetiklediğini toplar. Dosya referansları workspace-relative linklerle verildi.

## Nasıl okunur
- Sol: Kaynak / Event
- Sağ: Neopixel eylemi (preset/effect/anim) — nerede tanımlı

---

## Wakeword & Speech
- wakeword.detected ("hey sentry")
  - Neopixel: `TWINKLE` (jewel segment) + base `BREATHE`
  - Sahne: `wakeword_reaction` (see [modules/autonomy/config/config.yml](modules/autonomy/config/config.yml))
  - Kaynak: [modules/wakeword/xWakewordService.py](modules/wakeword/xWakewordService.py)

- speech.start
  - Neopixel: `RAINBOW_CYCLE` (interactions rule)
  - Kaynak: [modules/interactions/config/config.yml](modules/interactions/config/config.yml)

- speech.end
  - Neopixel: `COMET`
  - Kaynak: [modules/interactions/config/config.yml](modules/interactions/config/config.yml)

---

## Autonomy (Idle / Actions)
- LOOK_AROUND
  - Neopixel: `COMET` veya `curious_scan` preset
  - Robot anim: `look_around` (servo)
  - Kaynak: [modules/autonomy/services/brain.py](modules/autonomy/services/brain.py) (idle planner)

- BLINK
  - Neopixel: `RANDOM_BLINK`
  - Robot anim: `blink`

- STRETCH
  - Neopixel: `WAVE`
  - Robot anim: `stretch`

- SIGH / BORED
  - Neopixel: `PULSE` (yavaş/soft)
  - Robot: speak + mood change

- MONOLOGUE
  - Neopixel: `TWINKLE` veya `TWINKLE` + base
  - Robot: LLM monologue (speech)

Referans: [modules/autonomy/config/config.yml](modules/autonomy/config/config.yml)

---

## Vision
- vision.focus
  - Neopixel: `COMET` (short) + `vision_focus` anim
  - Kaynak: [modules/autonomy/services/brain_parts/vision.py](modules/autonomy/services/brain_parts/vision.py)

- vision.person (known)
  - Neopixel: `owner_welcome` preset + `COMET` burst
  - Robot anim: `owner_scan`, speak greeting
  - Kaynak: `scenes.vision_greeting_*` ([modules/autonomy/config/config.yml](modules/autonomy/config/config.yml))

---

## Owner / RFID / Temporary Owner
- owner.scan / owner_return
  - Neopixel: `owner_welcome` preset
  - Robot anim: `owner_scan`

- owner.temp_granted
  - Neopixel: `THEATER_CHASE` veya `temp_owner` preset (added)
  - Robot anim: `temp_owner`

- owner.temp_revoked / owner.locked
  - Neopixel: `PULSE` / `METEOR` (warning)

Referans: owner config in [modules/autonomy/config/config.yml](modules/autonomy/config/config.yml)

---

## System / Telemetry / Alerts
- error
  - Neopixel: `METEOR` (critical)
  - Kaynak: [modules/interactions/config/config.yml](modules/interactions/config/config.yml)

- warning
  - Neopixel: `PULSE`

- arduino_disconnected
  - Neopixel: `THEATER_CHASE` (magenta)

- cpu_temp / net_burst
  - Neopixel: `PULSE` / `COMET` or defined cpu palettes

---

## Mood / Emotion (Autonomy)
- Dominant emotion changes (Autonomy `_sync_emotion`) — now triggers scene `emotion_{name}`
  - emotion_joy → preset `emotion_joy` (RAINBOW_CYCLE + COMET), anim `look_around`
  - emotion_curiosity → preset `emotion_curiosity` (TWINKLE), anim `vision_focus`
  - emotion_fear → preset `emotion_fear` (PULSE red), small head move
  - emotion_tired → preset `emotion_tired` (BREATHE dim), `stretch` anim + head tilt
  - emotion_sad → preset `emotion_sad` (PULSE blue), downward tilt

Kod referansları:
- _sync_emotion logic: [modules/autonomy/services/brain.py](modules/autonomy/services/brain.py)
- Scenes: [modules/autonomy/config/config.yml](modules/autonomy/config/config.yml)
- Presets: [modules/neopixel/config/config.yml](modules/neopixel/config/config.yml)

---

## Interactions Engine (Rules → Effects/Bases)
Tüm önemli kurallar için özet:
- `speech.start` → `RAINBOW_CYCLE`
- `speech.end` → `COMET`
- `owner.scan` → `COMET`
- `owner.rfid` → `RAINBOW_CYCLE`
- `autonomy.excited` → `RAINBOW_CYCLE`
- `autonomy.blink` → `RANDOM_BLINK`
- `autonomy.look_around` → `COMET`
- `autonomy.stretch` → `WAVE`
- `autonomy.bored` → `PULSE`
- `autonomy.monologue` → `TWINKLE`
- `autonomy.sleep` → base `BREATHE` (dark)
- `autonomy.wake` → `COMET`
- `vision.focus` → `COMET`
- `vision.person` → `COMET`
- `error` → `METEOR`
- `warning` → `PULSE`

Tam kural listesi: [modules/interactions/config/config.yml](modules/interactions/config/config.yml)

---

## LLM / Ollama-driven actions
- `AutonomyBrain.apply_llm_response()` LLM yanıtındaki `actions` alanını işler; eğer `anim`/`effect`/`head` gibi eylemler dönerse bunlar direkt neopixel veya servo animasyonlarını tetikler.
- Referans: [modules/autonomy/services/brain.py](modules/autonomy/services/brain.py)

---

## Teknik akış (kısaca)
1. Robot modülü event atar (`push_interaction_event`) veya doğrudan `neopixel` endpoint çağırır.
2. `interactions` engine kuralı eşleşirse `NeoHttpClient` ile `neopixel` servisine HTTP çağrısı yapar.
3. `modules/neopixel` `NeoRunner.animate()` / `apply_preset()` çalıştırır.
4. `NeoDriver` donanıma (pi5neo) veya sim'e iletir.

İlgili kodlar:
- ServiceClient: [modules/autonomy/services/client.py](modules/autonomy/services/client.py)
- Interactions engine: [modules/interactions/services/engine.py](modules/interactions/services/engine.py)
- Neo runner: [modules/neopixel/services/runner.py](modules/neopixel/services/runner.py)

---

## Test örnekleri (hızlı)
- Interactions event (gateway üzerinden):

```
curl -X POST http://localhost:8080/interactions/event \
  -H 'Content-Type: application/json' \
  -d '{"type":"emotion.joy"}'
```

- Neo direct animate (neopixel servis):

```
curl -X POST 'http://localhost:8092/animate/run?name=COMET&speed=1.0&loop=false'
```

(Not: servis portları ortamınıza göre değişebilir; `modules/neopixel/config/config.yml` ve `modules/interactions/config/config.yml` içindeki `server.port` değerlerini kontrol edin.)

---

## Son notlar
- Eşlemeler proje içinde zaten çok büyük oranda tanımlıydı; eksik olan `emotion_*` ve `temp_owner` presetleri eklendi ve `_sync_emotion` artık scene çağırıyor.
- İstersen bu dosyayı CSV/JSON formatına da dönüştüreyim veya `README` içine özet olarak ekleyeyim.


## Semantik Pet İfade Kataloğu (Refactor)

> Otonomi, fiziksel LEDlere ham efekt adı göndermek yerine önce semantik niyet seçer. `GET /neopixel/companion/semantics` niyetin insan dilindeki açıklamasını; `POST /neopixel/companion/semantic` aynı niyeti göz ve iki kaş framei olarak uygular.

| Semantik niyet | Kullanıcıya görünen anlam | Görsel gerçekleştirme |
|---|---|---|
| `ambient_idle` | Sakin, uyanık ve çevreyi dinliyor. | BREATHE temelli nötr göz-kaş framei. |
| `quiet_observation` | Sessizce çevreyi gözlemliyor. | Nötr kaşlar ve yumuşak mavi göz. |
| `curious_scan` | Yeni bir nesne veya sesi merakla inceliyor. | WAVE ritmi, kalkık/kemerli kaşlar. |
| `social_greeting` | Tanıdık biriyle olumlu sosyal temas kuruyor. | PULSE, memnun kaş pozu ve sıcak göz. |
| `focused_attention` | Konuşanı ya da hedefi dikkatle dinliyor. | STACK, odaklanmış kaşlar ve altın göz. |
| `frustrated_cooldown` | Başarısızlıktan sonra güvenli biçimde sakinleşiyor. | GRADIENT, düşük enerjili turuncu ifade. |
| `sleep_transition` | Dinlenme/uyku moduna geçiyor. | SNOW, sönen göz ve uykulu kaşlar. |

### Ham Efektlerin Anlaşılır Sınıflandırması

| Efekt | Anlam / izinli kullanım |
|---|---|
| `EYE_EYEBROW` | Birleşik göz ve iki kaş pet yüz ifadesi; çevresel niyetlerde öncelikli efekt. |
| `BREATHE` | Sakin hazır olma, dinleme veya düşük enerjili boşta kalma. |
| `PULSE` | Kısa onay, olumlu fark ediş veya sosyal selamlama. |
| `WAVE`, `M_WAVE` | Merak, çevre tarama veya algılanan yeni hedefe yönelme. |
| `STACK` | Düşünme/işleme veya dikkatli dinleme. |
| `GRADIENT`, `M_GRAD` | Bir duygu/enerji durumundan diğerine yumuşak geçiş. |
| `TWINKLE` | Güvenli oyuncu/sosyal sevinç; uzun süreli boşta kullanım değil. |
| `CHASE`, `RUN`, `COMET` | Güvenli hedef takibi ya da odak hareketi; navigasyon reddedilirse yalnız yüz ifadesi kalır. |
| `BOUNCE` | Kısa, oyuncu keşif/sosyal davet; enerji ve güvenlik uygunsa. |
| `SNOW` | Uykuya geçiş, sakinleşme veya düşük enerjili dinlenme. |
| `RAINBOW`, `RAINBOW_CYCLE`, `ALT` | Dekoratif/parti/test efekti; otonomi bunları birincil duygu göstergesi olarak seçmez. |
| `METEOR`, `FIRE` | Uyarı, özel sahne veya tanılama; normal pet duygusunun varsayılanı değildir. |
| `WIPE`, `BLINK` | Kısa sistem geri bildirimi veya kalibrasyon; uzun süreli pet yüz ifadesi değildir. |

> Kural: Güvenlik ve sahiplik denetiminden geçmeyen ham animasyon çağrısı pet niyetini ezemez. Admin/test amaçlı dekoratif efektler semantik yüz frameinden ayrı tutulur.
