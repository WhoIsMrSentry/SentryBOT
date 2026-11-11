# Visual Output - OLED Faces

Robot durum ve olay sinyallerini Raspberry Pi SSD1306 OLED ekranda Pip tarzı prosedürel animasyonlu gözlere dönüştürür.

## Sorumluluklar

- Operational/emotion durumunu yüz animasyonuna çevirme
- Olay tabanlı gesture/activity/emotion gösterimi
- STT metnini geçici altyazı olarak gösterme
- Konuşma oturumu sırasında duygu debounce/kilitleme

## Mimari (Güncel: 2026-11-16)

- Giriş noktası: `xOledFacesService.py` (FastAPI `lifespan`, `time.monotonic()` süre tutarlılığı, fail-closed `claim_oled` + hata anında kiralama serbest bırakma)
- **Koordinatör**: `services/face_coordinator.py` → `FaceCoordinator` (state machine, event routing, `monotonic()` oturum süreleri)
- **Göz Motoru**: `services/eyes/`:
  - `engine.py` → `EyeEngine` (render loop, kilitli widget/altyazı anlık kopyası, modül seviyesi `_TR_MAP`, boş metinle altyazı sıfırlama, başlangıç `contrast` koruma)
  - `moods.py` → Mood render (`MOODS`)
  - `gestures.py` → Gesture animasyonları (`BLINKS`, `GESTURES_FN`)
  - `activities.py` → Activity modları (`ACTIVITIES`, `OVERLAYS`)
  - `activity_drawings.py` → Activity çizimleri (`_deploying` tampon reuse)
  - `vibes.py` → `VIBES` ve motor örneğine izole `VibeState`
  - `primitives.py` → Low-level çizim (ellipse, rounded_rect, heart, sparkle)
- **Sürücü**: `services/pi_ssd1306_driver.py` → `PiSsd1306Driver` (NumPy/PIL bit-pack, `_prev_buffer` dirty-page I2C delta yazımı, tam `RLock`, backoff ile otomatik I2C yeniden bağlanma, boşta `burn_in_dim_s` kontrast kısma ve `burn_in_sleep_s` `0xAE`/`0xAF` uyku/uyanma koruması)
- **Legacy Map**: `services/legacy_map.py` → Eski isim uyumluluğu
- **Idle Ambient**: `services/idle_ambient.py` → Boşta animasyon havuzu
- **Catalog Registry**: `services/catalog_registry.py` → Motor/activity/gesture kayıt
- **Mapper**: `services/mapper.py` → Event → mood/activity/gesture eşleme
- **Renderer**: `services/face_renderer.py` → `PiSsd1306Driver` + `EyeEngine` koordinasyonu

## Veri Kaynakları (Güncel Modül Yolları)

- `system_control/state_manager` → `operational`, `emotions` (global state)
- `expression/interactions` → Event akışı (metric events, companion events)
- `voice/speech` → `/oled_faces/stt_text` ile kısmi/final metin
- `common.emotion_vocab` → Kanonik duygu çözümlemesi (render hints)
- `autonomy` → Dominant mood, companion state
- `voice/speak` → Speech started/finished events (lip sync için)

## API (Gateway altında `/oled_faces/*`)

- `GET /oled_faces/healthz` (gerçek ekran/donanım durumu: `ok = bool(has_display)`)
- `GET /oled_faces/status` (`ok = bool(enabled and has_display)`)
- `GET /oled_faces/catalog` - Full motor/activity/gesture listesi
- `POST /oled_faces/manual` (`ManualRequest`: `mode`, `name`)
- `POST /oled_faces/event` (`EventRequest`: `type`, `data`; `speech.final`/`stt.final` altyazı sonrası erken döner)
- `POST /oled_faces/stt_text` (`SttTextRequest`: `text` boş string ile aktif altyazıyı temizler, `duration_s` doğrulaması yapılır)

## Konfigürasyon

`modules/visual_output/oled_faces/config/config.yml`:
- `display` I2C ayarları (`address`, `width`, `height`, `bus`, `contrast`, `dim_contrast`, `burn_in_dim_s`, `burn_in_sleep_s`)
- `event_map` - Event → mood/activity/gesture eşleme
- `idle_ambient.pool` - Boşta animasyon havuzu
- `idle_ambient.use_full_catalog: true` → Geniş mood/gesture/activity kataloğu (`use_full_catalog` bu alt anahtardır)

## İlişkiler (Güncel Modül Yolları)

- `expression` → OLED modality (`ExpressionArbiter` lease ile `claim_oled`)
- `autonomy` → Dominant duygu yansıması (mood → eye mood)
- `voice/speech` → Konuşma sırasında yüz/altyazı senkronu (listening/thinking/speaking)
- `expression/animate` → Animasyon sekanslarında OLED face frame'leri (attach_oled)
- `visual_output/neopixel` → Face frame koordinasyonu (companion_leds face_frame)

## ExpressionArbiter Lease

OLED kontrolü de **ExpressionArbiter** lease'ından geçer:
```python
arbiter.claim_oled(source="autonomy", priority=70, ttl_s=3.0)
```

**Öncelik:** `expression/animate` (90) > `autonomy` (70) > `interactions` (50) — bu **FaceCoordinator iç öncelik skalasıdır (74-100)**; ExpressionArbiter lease öncelikleri farklı bir skaladır (`modules/agent_core/config/config.yml` → `expression_lease.priorities`: autonomy 20, interactions 40, owner_command 60, safety_navigation 80, hardware_protection 90, emergency 100). İki skala karıştırılmamalı.

## Durum & Doğrulama

- `PiSsd1306Driver`, `FaceMapper`, `FaceCoordinator`, `EyeEngine`, router Pydantic uçları ve `ExpressionArbiter` kiralama kuralları `tests/modules/visual_output/oled_faces/` altındaki başsız (headless) birim testleriyle doğrulanır (`test_pi_ssd1306_driver.py`, `test_oled_faces_full.py`).