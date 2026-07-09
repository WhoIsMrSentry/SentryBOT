# SentryBOT — Companion Dönüşüm Planı (Devir-Teslim Dosyası)

> **Amaç:** Bu dosya, companion dönüşümü üzerinde çalışan herhangi bir AI'ın kaldığı yerden devam edebilmesi için tek kaynaktır.
> Her adım tamamlandığında checkbox işaretlenir ve "İlerleme Günlüğü"ne tarih + değişen dosyalar yazılır.
> Son güncelleme: 2026-07-09

## Vizyon

Robot; komutları gerçekten uygulayan (LED, duygu, konuşma…), hızlı yanıt veren, duyguları
nedenlerden doğan, öğrendiklerini davranışa yansıtan ve kamera gelince VLM'siz de çevresini
algılayan bir refakatçiye dönüşecek. Kararlar hardcoded kurallardan LLM + iç durum
(mood/ihtiyaç/hafıza) motoruna taşınacak. Dil desteği TR/EN hardcode'undan çıkarılıp
config-driven çok dilli yapıya geçecek.

## Teşhis Özeti (2026-07-09 keşif raporlarından)

### Tool-calling neden çalışmıyor
- `agent_core/services/tools.py` `ToolRegistry`'de 27 tool hazır (set_lights, set_emotion, oled_face, move_head, queue_action…).
- Tri-layer'da eylem yalnızca daraltılmış sub-agent adımında; persona katmanı (`_synthesize_main_persona`, agent.py ~956-1008) **tool'suz**.
- Router (`tri_layer.py` `_tokenize` ~285) yalnızca `[a-z0-9_]` kabul ediyor → "kırmızı", "üzgün" parçalanıyor.
- `autonomy` sub-agent izinli tool listesinde (`tri_layer.py` ~49-54) `set_lights` yok; fast profil `max_subagents` düşük → neopixel modülü rotaya giremiyor.
- Doğrudan `speak` tool'u yok ("şunu söyle X" çalışmıyor).
- `agent.step()` dönüşü her zaman `"actions": []` (agent.py ~1207-1214).
- Fallback `/ollama/chat` (ollama/services/chat.py) tool'suz düz metin; `extract_llm_tags` (tags.py) chat'e bağlı değil; autonomy fallback `apply_actions=false` gönderiyor (autonomy/services/client.py ~353).
- Native tam-tool loop `_run_native_history_loop` yalnızca subagent_reports boşken çalışıyor (agent.py ~1119-1121) → pratikte atlanıyor.

### Gecikme nereden geliyor
- "Putting the answer together" = `agent_core/services/progress.py` ~317-320 persona_start progress TTS'i (EN/TR hardcode).
- Zincir: wakeword min 1.5s dinleme (`xWakewordService.py` ~288-296) → autonomy 500ms poll + 0.8s debounce (`brain.py` ~201-209, ~252) → tri-layer çoklu LLM turu → sıralı bloklayan TTS (`speak` `/say`, Piper subprocess, streaming yok).
- Kullanılmayan streaming altyapısı: `/agent/step_stream` (SSE), `/speak/say_stream` (speak/api/router.py ~82-140), LLM `stream: False` (ollama/services/clients.py ~133).
- STT final'de dual-decode (TR+EN tam PCM ikinci geçiş, `stt_language.py` ~85-87).

### Companion/duygu eksikleri
- Mood 5 eksen + decay + appraisal altyapısı var; ama `appraisal.yml`'deki olayların çoğu kodda tetiklenmiyor (owner_returned, scene_change, alone_too_long, petted, darkness…).
- Karar dağılımı ~%70 kural/template, ~%25 LLM diyalog, ~%5 LLM otonom (`_make_agentic_decision` yalnızca sıkılınca %20 şansla).
- Öğrenilen tercihler (PreferenceLearner, moments, trust) yalnızca sohbet bağlamına ekleniyor; davranış seçimini etkilemiyor.
- Write-only tablolar: sightings, mood_snapshots, interaction_events (karar okumuyor); owner_sessions prod'da hiç kullanılmıyor.
- Hardcoded karar noktaları listesi: bkz. Ek A.

### Vision/IMX500 durumu
- `camera/services/imx500_runner.py` + `onsensor_bus.py` yazılmış (SSD MobileNetV2, picamera2 IMX500). Kamera `enabled: false`.
- Yerel (VLM'siz) çalışabilen: Haar yüz algılama, ORB+FLANN kişi tanıma (social_db face_descriptors), CSRT takip, IMX500 bbox, mesafe, selamlama.
- Yerel yüz-duygu tanıma YOK (emotion alanı yalnız remote ingest/VLM'den).
- `vision_event_bus.py`'de tanımlı ama publish edilmeyen: EVENT_PERSON_SEEN, EVENT_PERSON_LOST, EVENT_FOLLOW_START/STOP.
- FaceManager yalnızca `processing_mode == "local"` init'te oluşuyor (processor.py ~172-181) — mod geçişinde eksik.
- İki bağımsız kafa kontrol hattı: speech `pan_tilt.py` (yalnız pan, doğrudan Arduino) vs vlm `HeadControlArbiter` (pan+tilt, öncelikli).

---

## Fazlar ve Checklist

### Faz 0 — Devir-teslim dosyası
- [x] Bu dosya oluşturuldu.

### Faz 1 — LLM robota komut verebilsin (tool-calling onarımı)
- [x] **1.1 Router Türkçe/unicode düzeltmesi**
- [x] **1.2 Sub-agent tool kapsamı**
- [x] **1.3 `speak` tool**
- [x] **1.4 step() actions dolulukları**
- [x] **1.5 Direct-command fast-path**
- [x] **1.6 Gemma prompt-based tool parse sağlamlaştırma**
- [x] **1.7 Fallback yolu**

### Faz 2 — Gecikme + streaming
- [x] **2.1 Fast-path** — tek LLM turu, `num_predict: 96`, progress ack TTS kapalı.
- [x] **2.2 LLM streaming → cümle-cümle TTS** — tri-layer persona stream + fast-path cümle enqueue.
- [x] **2.3 Event-driven speech** — `/autonomy/speech` push; debounce `0.35s`.
- [x] **2.4 Progress TTS sadeleştirme** — fast-path'te ack konuşmaz; persona_start eşik config'te.
- [x] **2.5 Wakeword/STT tuning** — min_listen 1.0s (VAD 0.75s); dual-decode yalnız belirsiz dilde.

### Faz 2b — Çok dilli ses hattı (hardcode kaldır)
- [x] **2b.1 Dil algılama** — `langdetect` + `prefer_online_detect`; `dual_decode_languages` config; TR/EN dışı modeller varsa multi-decode.
- [x] **2b.2 Dil uçtan uca taşınsın** — STT → autonomy event → agent `session_language` → TTS Piper/fallback zinciri.
- [x] **2b.3 TTS ses seçimi** — Piper yoksa `piper.fallback_engine` (pyttsx3); config-driven `language_voices`.
- [x] **2b.4 Progress TTS i18n** — `progress_messages.yml` 14 dil; `persona_start_min_elapsed_s` ile hızlı isteklerde filler yok.

### Faz 2c — NeoPixel VU-meter + Jewel
- [x] **2c.1 Layout config** — `neopixel/config.yml` jewel 0-6, stick 7-16.
- [x] **2c.2 VU_METER** — `CompanionLedController` stick seviye; `speech.audio_level` event → interactions → neo.
- [x] **2c.3 JEWEL_THINKING** — mavi karşılı atlamalı desen + merkez göz pulse; `agent.processing.start`.
- [x] **2c.4 JEWEL_EYE** — merkez LED nefes; dinleme/konuşma modları.
- [x] **2c.5 Interactions kuralları** — wakeword, speech.listen/start/end, agent.processing start/end.

### Faz 3 — Duygu ve karar motoru
- [x] **3.1 Appraisal olaylarını bağla** — owner_returned, scene_change, alone_too_long, new_person, hazard, command_ok/failed.
- [x] **3.2 Needs modeli** — social/stimulation/rest eksenleri config-driven.
- [x] **3.3 LLM karar döngüsü** — ihtiyaç eşiği tetiklemesi, mood trend + sightings özeti, rate-limit config.
- [x] **3.4 Öğrenme → davranış** — agentic prompt'ta social context, mood trend, sightings.
- [x] **3.5 Duygu komut kısayolu daralt** — yalnız 1-2 kelimelik imperatifler; uzun cümleler LLM'e.

### Faz 4 — IMX500 hazırlığı (kod hazır, config kapalı)
- [x] **4.1 FER servisi** — `face_emotion.py` (heuristic/onnx); PersonContext.emotion yerel dolar.
- [x] **4.2 Eksik event publish** — PERSON_SEEN/LOST, FOLLOW_START/STOP processor'da.
- [x] **4.3 FaceManager lazy-init** — `set_processing_mode("local")` geçişinde oluşturulur.
- [x] **4.4 Kafa kontrol birleştirme** — speech pan → `/vlm/head/move` arbiter (priority 60).
- [x] **4.5 Aktivasyon checklist** — bkz. Ek 4.5 (config referansı).

### Faz 5 — Test
- [x] Yeni birim testleri: needs, FER, head arbiter, STT ambiguous, emotion shortcut, progress i18n, companion LEDs, appraisal triggers.
- [x] Companion modül testleri yeşil (264 passed: agent_core, autonomy, speech, vlm_bridge, neopixel, interactions, speak).
- [x] `python -m pytest modules/ -q --maxfail=1` tam suite — **437 passed** (Faz 6 testleri dahil).
- [ ] Manuel doğrulama listesi (robot üstü): aşağıda Ek B.

### Faz 6 — Kalan appraisal + dil iyileştirmeleri
- [x] **6.1 Kalan appraisal olayları** — `user_thanks`, `user_insult`, `petted`, `played_with`, `owner_left`, `owner_lockout`, `darkness`, `rested`, `greeted` (`appraisal_triggers.py` + brain/vision/owner_guard).
- [x] **6.2 Gerçek token streaming** — `_chat_maybe_stream` Ollama token → cümle callback; native loop + tüm step yollarında `on_sentence`; fast-path cümle enqueue.
- [x] **6.3 Template katmanı azaltma** — `companion_lines.py` (needs + opsiyonel LLM); `proactive_planner` / `companion_rituals` yeniden yazıldı.
- [x] **6.4 DeepFace remote FER** — `face_emotion.backend: remote`, `POST /vlm/fer/analyze` (DeepFace → heuristic fallback).

---

## İlerleme Günlüğü

| Tarih | Adım | Değişen dosyalar | Not |
|-------|------|------------------|-----|
| 2026-07-09 | Faz 0 | `.sentrybot/context/companion-upgrade-plan.md` | Dosya oluşturuldu |
| 2026-07-09 | 1.1-1.2 | `tri_layer.py` | `_tokenize` unicode (`\w+`), `_LIGHT_TOKENS` prior (TR renk/ışık kelimeleri, neopixel boost 3.5), autonomy sub-agent tools genişletildi (set_lights, oled_face, move_head, play_sound, speak, queue_action), speak/neopixel profillerine TR keyword |
| 2026-07-09 | 1.3 | `tools.py` | `speak(text, tone, language)` tool eklendi → queue_action("speak", priority=60) sarmalayıcı |
| 2026-07-09 | 1.4 | `agent.py` | `_run_native_history_loop(actions_out=...)`, `_run_subagent` rapora `actions` ekler, `_summarize_actions`, persona payload'ına `actions_taken`, `step()` dönüşünde gerçek `actions` |
| 2026-07-09 | 1.5 | `agent.py`, `modules/agent_core/config/config.yml`, `config/agent.yaml` | `tri_layer.fast_path {enabled, max_chars:140}`: kısa istekler tri-layer'ı atlar, `_native_loop_messages` (persona system prompt + tam tool seti) ile tek loop |
| 2026-07-09 | 1.6 | `agent.py` | `_loads_first_json_object` (balanced-brace parse), tool/tool_name/name + arguments/args/parameters alias'ları, `_chat_via_provider` tool_call/tool_result mesajlarını metinleştirir (çok-turlu Gemma döngüsü) |
| 2026-07-09 | 1.7 | `modules/ollama/services/chat.py`, `modules/autonomy/services/client.py` | Chat çıkışına `extract_llm_tags` bağlandı (actions payload'da), autonomy client `apply_actions=None` → ollama config default'una bırakır |
| 2026-07-09 | 2b.4 | `modules/agent_core/config/progress_messages.yml` (yeni), `progress.py`, `agent.py` | 14 dilli progress kataloğu; `_msg/_msg_choice/_msg_map` + EN fallback; `persona_start_min_elapsed_s: 4.0` (hızlı istekte "yanıt hazırlıyorum" konuşulmaz); `_language_directive` artık her ISO kodunu destekler (hardcode TR/EN kalktı) |
| 2026-07-09 | 2b.1-2b.3 | `modules/speak/services/lang_detect.py`, `tts.py`, `config/agent.yaml`, `modules/speak/config/config.yml`, `modules/speak/requirements.txt` | `has_piper_voice_for_language`; Piper sesi olmayan dilde `piper.fallback_engine` (pyttsx3) devreye girer; langdetect speak requirements'a eklendi; test `test_stt_language.py` yeni API'ye uyarlandı |
| 2026-07-09 | 2c | `companion_leds.py`, `runner.py`, `api/router.py`, `neopixel/config.yml`, `interactions/config.yml`, `interactions/engine.py`, `speech/api/router.py`, `progress.py`, `agent.py`, `stt_language.py`, `xSpeechService.py` | VU-meter (stick 7+), jewel thinking/eye (0-6), interactions event kuralları, speech.audio_level RMS, agent.processing start/end, çok dilli STT dual_decode_languages |
| 2026-07-09 | 2.1-2.5 | `agent.py`, `progress.py`, `config.yml`, `stt_language.py`, `xWakewordService.py`, `autonomy/config.yml` | Fast-path num_predict, progress ack skip, cümle streaming fast-path, speech debounce 0.35s, dual_decode_only_if_ambiguous, VAD-linked min_listen |
| 2026-07-09 | 3.1-3.5 | `brain.py`, `mood.py`, `owner_guard.py`, `vision.py`, `autonomy/config.yml` | Appraisal wiring, needs model, agentic need triggers, emotion shortcut 1-2 kelime |
| 2026-07-09 | 4.1-4.4 | `face_emotion.py`, `processor.py`, `control.py`, `head_control_arbiter.py`, `xSpeechService.py`, `vlm_bridge/config.yml` | FER heuristic/onnx, vision events, FaceManager lazy-init, speech→head arbiter |
| 2026-07-09 | 5 | `test_needs_model.py`, `test_face_emotion.py`, `test_head_sound_direction.py`, `test_stt_ambiguous.py`, `test_emotion_commands.py` | 264 companion-module tests passed |
| 2026-07-09 | 5b | Pillow kurulumu, `translator.py` TR heuristic | Tam suite **433 passed** |
| 2026-07-09 | 6.1 | `appraisal_triggers.py`, `brain.py`, `owner_guard.py`, `vision.py`, `test_appraisal_triggers.py` | Kalan appraisal olayları bağlandı |
| 2026-07-09 | 6.2 | `agent.py`, `test_streaming_chat.py` | `_chat_maybe_stream`: Ollama token stream → cümle callback; native loop streaming |
| 2026-07-09 | 6.3 | `companion_lines.py`, `proactive_planner.py`, `companion_rituals.py`, `brain.py`, `autonomy/config.yml`, `test_companion_lines.py` | Needs-driven + opsiyonel LLM satır üretimi; template havuzları azaltıldı |
| 2026-07-09 | 6.4 | `face_emotion.py`, `vlm_bridge/api/analysis.py`, `vlm_bridge/config.yml`, `processor.py`, `test_face_emotion_remote.py` | Remote FER backend + `/vlm/fer/analyze` endpoint |
| 2026-07-09 | 5c | tüm Faz 6 testleri | Tam suite **437 passed** |

---

## Ek A — Hardcoded karar noktaları (tespit, 2026-07-09)

| Konum | Kural |
|-------|-------|
| `mood.py` 72-93 | Dominant emotion eşikleri (if/else) |
| `mood.py` 51-65 | Sabit decay katsayıları |
| `brain.py` 341-353 | Keyword sentiment → praise/rude |
| `brain.py` 369-406 | Emotion command phrase listesi |
| `brain.py` 409-433 | Emotion command sabit cevaplar (TR/EN) |
| `brain.py` 492-507 | Boredom 20s, idle 6s, LLM fallback %20 |
| `proactive_planner.py` 80-137 | Mood/owner template havuzları |
| `companion_rituals.py` 76-104 | Sabit "Günaydın…" cümleleri |
| `vision.py` 134-142, 219-235 | Empati/selamlama sabit cümleler + eşik |
| `owner_guard.py` 56-64, 96-116 | restricted_keywords, sabit mesajlar |
| `brain.py` 1235, 1245 | Uyku/uyanma sabit cümleler |
| `progress.py` 317-320 | "Putting the answer together" EN/TR |
| `interactions/config.yml` 40-207 | Event→LED sabit eşleme (bu kalabilir — refleks katmanı) |

## Ek B — Manuel doğrulama listesi (robot üstü)

- "Neopixelleri kırmızı yap" → LED'ler kırmızı olmalı, yanıt eylemi teyit etmeli.
- "Duygu durumunu üzgün yap" → OLED+LED+kulak üzgün; state_manager emotions=["sadness"].
- "Şunu söyle: günaydın" → robot aynen "günaydın" demeli.
- Almanca/İspanyolca soru → aynı dilde yanıt; Piper modeli yoksa fallback TTS.
- Wakeword sonrası şerit LED'ler VU-meter; işlem sırasında jewel mavi düşünme deseni; merkez LED duygu renginde.
- Basit soru ("saat kaç") yanıt süresi belirgin kısalmalı; "Putting the answer together" duyulmamalı (fast-path).
- Sıkılınca robotun kendi kararıyla bir eylem yaptığı gözlemlenmeli (log: agentic decision).
- Kamera takılınca Ek 4.5 checklist uygulanıp kişi takibi + selamlama + FER duygu aynası test edilmeli.

## Ek 4.5 — Kamera aktivasyon checklist (Pi)

```yaml
# config/agent.yaml veya modül config'leri
camera.enabled: true
camera.backend: picamera2
camera.imx500.enabled: true
vlm_bridge.vision.processing_mode: local
vlm_bridge.vision.mode_categories.onsensor.tiny_detect: true
vlm_bridge.vision.follow.enabled: true
vlm_bridge.vision.face_emotion.backend: heuristic  # veya onnx + model_path
# Tamamen yerel: vision_llm.enabled: false
```

## Ek C — Önemli dosya haritası

| Alan | Dosyalar |
|------|----------|
| Agent orkestrasyon | `modules/agent_core/services/agent.py`, `tri_layer.py`, `tools.py`, `progress.py`, `speech_arbiter.py`, `action_arbiter.py` |
| Otonomi | `modules/autonomy/services/brain.py`, `brain_parts/*`, `mood.py`, `affective_appraisal.py`, `expression_director.py`, `proactive_planner.py`, `client.py` |
| Ses giriş | `modules/wakeword/xWakewordService.py`, `modules/speech/xSpeechService.py`, `services/recognizer.py`, `stt_language.py`, `direction.py`, `pan_tilt.py` |
| Ses çıkış | `modules/speak/xSpeakService.py`, `services/tts.py`, `player.py`, `api/router.py` |
| LLM | `modules/ollama/services/chat.py`, `clients.py`, `tags.py`, `translator.py` |
| Vision | `modules/vlm_bridge/services/processor.py`, `vision_event_bus.py`, `face_manager.py`, `person_identity.py`, `head_control_arbiter.py`; `modules/camera/services/imx500_runner.py`, `onsensor_bus.py` |
| LED | `modules/neopixel/` (xService + api/router) |
| Config | `config/agent.yaml` (merkez), modül `config/config.yml` dosyaları |
