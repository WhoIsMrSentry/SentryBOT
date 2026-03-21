# Neopixel Event → Animasyon Eşlemesi

Bu doküman, repodaki tetikleyiciler (wakeword, speech, autonomy, vision, owner, system, mood, vb.) ile Neopixel animasyon/preset/effect çağrıları arasındaki tam eşlemeyi içerir.

## Özet akış
- Robot modülleri (`autonomy`, `wakeword`, `speech`, vb.`) `ServiceClient` veya `interactions` üzerinden `neopixel`/`interactions` servislerine istek atar.
- `modules/interactions` kuralları event → effect/base eşlemelerini uygular.
- `modules/neopixel` `NeoRunner.animate()` veya `apply_preset()` ile donanıma gönderir.

## Tam Eşleme (Kaynak/Event → Neopixel eylem) 
- `wakeword.detected` / "hey sentry"
  - Neopixel: `TWINKLE` (jewel segment), base `BREATHE`, COMET burst
  - Nerede: `modules/autonomy/config/config.yml` → `scenes.wakeword_reaction`

- `speech.start`
  - Neopixel: `RAINBOW_CYCLE` (kısa)
  - Nerede: `modules/interactions/config/config.yml` kuralı `speech_start`

- `speech.end`
  - Neopixel: `COMET`
  - Nerede: `modules/interactions/config/config.yml` kuralı `speech_end`

- `autonomy.excited`
  - Neopixel: `RAINBOW_CYCLE`
  - Nerede: interactions kural `autonomy_excited`

- `autonomy.look_around` / Idle LOOK_AROUND
  - Neopixel: `COMET` veya preset `curious_scan`
  - Nerede: interactions kural `autonomy_look_around` ve scene `curious_scan`

- `autonomy.blink` / BLINK
  - Neopixel: `RANDOM_BLINK`
  - Nerede: interactions kural `autonomy_blink`

- `autonomy.stretch` / STRETCH
  - Neopixel: `WAVE`
  - Nerede: interactions kural `autonomy_stretch`

- `autonomy.bored` / SIGH
  - Neopixel: `PULSE` (soft)
  - Nerede: interactions kural `autonomy_bored`

- `autonomy.monologue`
  - Neopixel: `TWINKLE` + base
  - Nerede: interactions kural `autonomy_monologue`

- `vision.focus`
  - Neopixel: `COMET` + anim `vision_focus`
  - Nerede: `brain_parts.vision` ve interactions `vision_focus` kuralı

- `vision.person` / `vision_greeting_*`
  - Neopixel: `owner_welcome` preset (jewel pulse + stick color), COMET burst
  - Nerede: scenes `vision_greeting_*`

- `owner.scan` / `owner_return`
  - Neopixel: `owner_welcome` preset + COMET
  - Nerede: scenes `owner_return`

- `owner.temp_granted`
  - Neopixel: `THEATER_CHASE` veya preset `temp_owner` (eklenen)
  - Nerede: interactions / owner flow

- `owner.temp_revoked` / `owner.locked`
  - Neopixel: `PULSE` / `METEOR` (uyarı)

- `error` / `warning`
  - Neopixel: `METEOR` (error), `PULSE` (warning)
  - Nerede: interactions kuralları `error_ping`, `warning_ping`

- `arduino_disconnected`
  - Neopixel: `THEATER_CHASE` (magenta)
  - Nerede: interactions kural `arduino_disconnected`

- `net_burst` / `cpu_temp` uyarıları
  - Neopixel: `COMET` / `PULSE` renk bazlı uyarılar

- Duygu/Mood (dominant emotion değişiklikleri)
  - `emotion_joy` → preset `emotion_joy` (RAINBOW_CYCLE + COMET), `look_around` anim
  - `emotion_curiosity` → preset `emotion_curiosity` (TWINKLE), `vision_focus` anim
  - `emotion_fear` → preset `emotion_fear` (PULSE kırmızı), kısa head hareket
  - `emotion_tired` → preset `emotion_tired` (BREATHE koyu), `stretch` anim + tilt
  - `emotion_sad` → preset `emotion_sad` (PULSE mavi), küçük tilt
  - Nerede: `modules/autonomy/services/brain.py` `_sync_emotion` (yeni) ve `modules/autonomy/config/config.yml` sahneleri

- LLM / Ollama yanıtlarından gelen `actions`
  - Neopixel: LLM `actions` içindeki `effect` / `anim` tetikler (dinamik)
  - Nerede: `AutonomyBrain.apply_llm_response()` ve `_handle_llm_actions`

## Teknik Yol (hangi fonksiyon / dosya)
- Event üreticiler: `modules/wakeword/xWakewordService.py`, `modules/autonomy/services/brain.py` (sense/think), `modules/speech`
- Interaction routing: `modules/interactions/services/engine.py` (kurallar ve NeoHttpClient)
- Neopixel server: `modules/neopixel/services/runner.py` → `NeoRunner.animate()` / `apply_preset()`
- Donanım sürücüsü: `modules/neopixel/services/driver.py` (`NeoDriver`, `pi5neo` veya sim)

## Test örnekleri (curl ile)
- `speech.start` event simülasyonu:

```bash
curl -X POST http://localhost:8095/interactions/event -H 'Content-Type: application/json' -d '{"type":"speech.start"}'
```

- `emotion.joy` event simülasyonu (alternatif):

```bash
curl -X POST http://localhost:8095/interactions/event -H 'Content-Type: application/json' -d '{"type":"emotion.joy"}'
```

- `vision.focus` simülasyonu:

```bash
curl -X POST http://localhost:8095/interactions/event -H 'Content-Type: application/json' -d '{"type":"vision.focus", "data": {"label":"person"}}'
```

(Port ve endpointler runtime konfigürasyonuna göre değişir; örnekler config içindeki `endpoints` ve servis portlarına göredir.)

## Notlar & Öneriler
- Pi backend kullanıldığında segment/preset doğrudan çalışır; ESP (`neo.ino`) backend kullanılıyorsa segment param parsing eklenmeli.
- Preset ve effect isimlerinde tutarlılık korundu; `NeoRunner` ve `neo.ino` fonksiyon isimleri işlevsel olarak eşleşmektedir.
- Bu dosya güncel eşlemeyi içerir; istersen CSV/JSON formatına çevirip `docs/` altına da kaydederim.

---
Kaydedildi: `docs/neopixel_event_mapping.md`