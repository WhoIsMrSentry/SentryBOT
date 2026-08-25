# Visual Output - OLED Faces

Robot durum ve olay sinyallerini Raspberry Pi SSD1306 OLED ekranda Pip tarzı prosedürel animasyonlu gözlere dönüştürür.

## Sorumluluklar

- Operational/emotion durumunu yüz animasyonuna çevirme
- Olay tabanlı gesture/activity/emotion gösterimi
- STT metnini geçici altyazı olarak gösterme
- Konuşma oturumu sırasında duygu debounce/kilitleme

## Mimari (Güncel: 2026-08-20)

- Giriş noktası: `xOledFacesService.py`
- **Koordinatör**: `services/face_coordinator.py` → `FaceCoordinator` (state machine, event routing)
- **Göz Motoru**: `services/eyes/`:
  - `engine.py` → `EyeEngine` (render loop, frame generation)
  - `moods.py` → Mood render (neutral, happy, sad, angry, curious, vb.)
  - `gestures.py` → Gesture animasyonları (blink, look, scan, wink)
  - `activities.py` → Activity modları (thinking, listening, speaking, scanning, idle)
  - `activity_drawings.py` → Activity çizimleri (activities.py'den ayrıldı)
  - `primitives.py` → Low-level çizim (ellipse, line, bitmap)
- **Sürücü**: `services/pi_ssd1306_driver.py` → `SSD1306Driver` (I2C, buffer, PIL conversion)
- **Legacy Map**: `services/legacy_map.py` → Eski isim uyumluluğu
- **Idle Ambient**: `services/idle_ambient.py` → Boşta animasyon havuzu
- **Catalog Registry**: `services/catalog_registry.py` → Motor/activity/gesture kayıt
- **Mapper**: `services/mapper.py` → Event → mood/activity/gesture eşleme
- **Renderer**: `services/face_renderer.py` → Frame composition

## Veri Kaynakları (Güncel Modül Yolları)

- `system_control/state_manager` → `operational`, `emotions` (global state)
- `expression/interactions` → Event akışı (metric events, companion events)
- `voice/speech` → `/oled_faces/stt_text` ile kısmi/final metin
- `common.emotion_vocab` → Kanonik duygu çözümlemesi (render hints)
- `autonomy` → Dominant mood, companion state
- `voice/speak` → Speech started/finished events (lip sync için)

## API (Gateway altında `/oled_faces/*`)

- `GET /oled_faces/healthz`
- `GET /oled_faces/status`
- `GET /oled_faces/catalog` - Full motor/activity/gesture listesi
- `POST /oled_faces/manual` (`mode`: `bitmap`|`animation`|`logo`)
- `POST /oled_faces/event` (`type`, opsiyonel `data`)
- `POST /oled_faces/stt_text` (speech modülünden beslenir)

## Konfigürasyon

`modules/visual_output/oled_faces/config/config.yml`:
- `display` I2C ayarları (`address`, `width`, `height`, `bus`)
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

## Bilinen Sorunlar

1. **FaceCoordinator + EyeEngine Çok Büyük** - `engine.py` 248, `activities.py` 102, `moods.py` 221 satır. `activities.py` çizimleri `services/eyes/activity_drawings.py`'a taşındı; `EyeEngine` render loop + frame generation ayrılmalı.
2. **Legacy Map Yüzde 80+ Kullanım** - `legacy_map.py` 136 satır, eski config isimleri hâlâ destekleniyor. Temizleme planlanmalı.
3. **Driver Headless Test Eksik** - `pi_ssd1306_driver.py` donanıma bağlı, CI'de mock test yok.