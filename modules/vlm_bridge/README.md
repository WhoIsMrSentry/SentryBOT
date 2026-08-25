# VLM Bridge

SentryBOT'un görsel algı ve köprü modülüdür. Yerel OpenCV pipeline'ı veya uzak VLM sonuç ingest'i ile yüz/kişi/nesne bağlamını üretir; takip, hafıza ve otonomi entegrasyonunu sağlar.

## Sorumluluklar

- **Local mode**: Haar/OpenCV yüz algılama + ORB/FLANN tanıma + CSRT takip
- **Remote mode**: Dış işlemciden (PC) `/vlm/results` ingest (HTTP)
- **On-sensor mode**: IMX500 hardware accelerator (object detection)
- Yüz takibi, owner follow, **HeadControlArbiter** (priority lease)
- Kişi hafızası (`PersonIdentity`), görsel bağlam cache'i, semantic scene
- Autonomy'ye action dispatch (`apply_actions` → `/autonomy/apply_actions`)
- Vision event bus ve request gate (rate limiting, cooldown, budget)

## Mimari (Güncel: 2026-08-20) - **PARÇALANMIŞ**

- Giriş noktası: `xVlmBridgeService.py`
- **Processor Parçaları** (eski `services/processor.py` 1871 satır → 8 dosya):
  - `services/processor_init.py` → `VisionProcessor.__init__`, config, dependencies
  - `services/processor_vlm.py` → VLM client, budget gate, inference
  - `services/processor_identity.py` → `PersonIdentity` (face register, recognize, remember)
  - `services/processor_identity_events.py` → Identity event handlers
  - `services/processor_follow.py` → Follow mode (owner tracking, focus)
  - `services/processor_stream.py` → Stream processing, capture loop, IMX500
  - `services/processor_modes.py` → Mode management, profiles, categories
  - `services/processor_vlm_signals.py` → Vision signals, event bus
  - `services/runtime_vision.py` → Runtime vision context, living vision
- **Diğer Servisler**:
  - `services/action_dispatcher.py` → `ActionDispatcher` (autonomy apply_actions)
  - `services/face_manager.py` → Face detection/tracking (CSRT)
  - `services/google_vlm_client.py` → Google Cloud VLM / Gemini client
  - `services/llm_client.py` → LLM semantic scene generation
  - `services/head_control_arbiter.py` → **HeadControlArbiter** (priority lease, clamping)
  - `services/ollama_vlm_client.py` → Ollama VLM client
  - `services/cascade_loader.py` → Cascade yapılandırma yükleyici
  - `services/vision_event_bus.py` → Vision event bus
  - `services/semantic_describer.py` → Semantic scene açıklama üretimi
  - `services/face_emotion.py` → Yüz duygu analizi (FER)
  - `services/budgeted_inference.py` → Bütçe kontrollü VLM inference
- **API Parçaları**: `api/control.py`, `api/config_routes.py`, `api/analysis.py`, `api/person.py`

## Mod Yönetimi

- `processing_mode`: `local` | `remote` | `onsensor` (IMX500)
- **Production (Pi)**: `local` + `hybrid_local_capture: true` via `config/robot_execution_profiles.json` `vision`
- PC / YAML override: `follow_runtime_profile: false` keeps explicit remote ingest
- **Mod Bayrakları**: `objects`, `people`, `faces`, `depth`, `ocr`, `hazards`, `semantic_scene`
- **Kategori Haritası**: `local` / `remote` / `onsensor` hangi mod hangi kategoride çalışır
- **Profiller**: `balanced`, `people_focus`, `objects_focus`, `assistive`, `minimal`
- **Realtime Profiller**: `fast`, `normal` (VLM timeout/interval tuning)

## API (Gateway altında `/vlm/*`)

### Kontrol / Takip
- `POST /vlm/track` - Head pan/tilt komutu (HeadControlArbiter lease ile)
- `POST /vlm/follow/start|stop`, `GET /vlm/follow/status`
- `POST /vlm/follow/owner/start` - Owner follow mode
- `POST /vlm/focus/person` - Person focus
- `GET /vlm/head/status`, `POST /vlm/head/move`

### Mod / Profil
- `GET|POST /vlm/mode` - Mode bayrakları toggle
- `GET|POST /vlm/modes/categories` - Kategori haritası
- `GET /vlm/profile`, `POST /vlm/profile/switch` - Profil değiştir

### Sonuç / Bağlam
- `GET /vlm/results/latest` - Son VLM/OpenCV sonucu
- `POST /vlm/results` - Remote ingest (PC → Pi)
- `GET /vlm/context/latest` - Living vision context
- `POST /vlm/context/refresh` - Manuel refresh

### Analiz
- `POST /vlm/analyze` - Frame analizi (local/remote)
- `POST /vlm/ask` - VLM soru-cevap
- `POST /vlm/ocr` - OCR
- `POST /vlm/fer/analyze` - Facial emotion recognition
- `GET /vlm/video_feed` - MJPEG stream

### Yüz / Hafıza
- `POST /vlm/faces/register`, `GET /vlm/faces`
- `POST /vlm/person/remember`, `POST /vlm/person/relationship`
- `GET /vlm/person/{name}`, `GET /vlm/people`
- `POST /vlm/memory/chat`, `GET /vlm/memory/person`, `GET /vlm/memory/people`

### Assistive
- `POST /vlm/blind/start|stop` - Görme engelliler için scene description

## Konfigürasyon

Merkezi `config/agent.yaml` → `vlm_bridge` section + modül-içi `config/config.yml` (merge):

- `vision.processing_mode` - `local|remote|onsensor`
- `vision.hybrid_local_capture` - bool
- `vision_llm` / `google_vlm_client` - LLM/VLM client config
- `remote_multimodal` - PC endpoint config (`base_url`, `chat_endpoint`, `analyze_endpoint`)
- `actions.endpoint` - Genelde `/autonomy/apply_actions`
- `vision_request_gate` - Rate limit, cooldown, budget config
- `head_control_arbiter` - Priority, TTL, clamp settings

## İlişkiler (Güncel Modül Yolları)

- `autonomy` → Vision hooks, selamlama, world-memory beslemesi (`vision_context_bridge`)
- `camera` → Local capture kaynağı (`CameraCapture`, `Imx500Runner`)
- `arduino_serial` → Head/track komutları (HeadControlArbiter → `arduino.track()`)
- `expression/interactions` → Görsel olayların ifadeye dönüşümü
- `ai_provider` (eski `ollama`) / `google_vlm_client` → Semantic scene üretimi
- `cognitive_memory` (eski `social_db`) → Person/face memory persist
- `visual_output/oled_faces` → Face focus koordinasyonu

## HeadControlArbiter (KRİTİK)

Tüm head hareketi (track, follow, focus) **HeadControlArbiter**'dan geçer:
```python
arbiter.claim(source="vlm_follow", priority=85, ttl_s=1.0, pan=20, tilt=-5)
arbiter.clamp(pan, tilt)  # Deadband, slew rate, limits
```
- **Priority**: `animate` (90) > `vlm_follow` (85) > `autonomy_vision` (80) > `speech_doa` (70)
- **Clamping**: Deadband (0.5°), slew rate (deg/s), min/max limits
- **Bypass Riski**: `expression/animate` ve `autonomy` doğrudan `arduino.track()` çağırıyor!

## Bilinen Sorunlar

1. **Processor Parçalanma Tamamlandı Ama Facade Hala Var** - `VisionProcessor` artık thin facade olmalı, tüm mantık `processor_*.py`'larda.
2. **HeadControlArbiter Bypass** - `expression/animate` (animasyon sekansları) ve `autonomy/brain_parts/animations.py` doğrudan `arduino.track()` çağırıyor. **Tüm head hareketi arbiter'dan geçmeli.**
3. **Memory Yazma Çakışması** - `processor_identity.py` → `cognitive_memory` DB'sine yazıyor, `autonomy` de yazıyor. Transaction isolation yok.
4. **Budget Gate** - `vision_request_gate` + `vlm_inference_budget_gate` var ama `google_vlm_client` bazen bypass ediyor.