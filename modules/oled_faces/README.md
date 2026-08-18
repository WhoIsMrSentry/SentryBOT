# OLED Faces

Robot durum ve olay sinyallerini Raspberry Pi SSD1306 OLED ekranda Pip tarzı prosedürel animasyonlu gözlere dönüştürür.

## Sorumluluklar

- Operational/emotion durumunu yüz animasyonuna çevirme
- Olay tabanlı gesture/activity/emotion gösterimi
- STT metnini geçici altyazı olarak gösterme
- Konuşma oturumu sırasında duygu debounce/kilitleme

## Mimari

- Giriş noktası: `xOledFacesService.py`
- Koordinatör: `services/face_coordinator.py`
- Göz motoru: `services/eyes/` (moods, gestures, activities)
- Sürücü: `services/pi_ssd1306_driver.py`
- Legacy isim eşlemesi: `services/legacy_map.py`

## Veri Kaynakları

- `state_manager`: `operational`, `emotions`
- `interactions`: event akışı
- `speech`: `/oled_faces/stt_text` ile kısmi/final metin
- `common.emotion_vocab`: kanonik duygu çözümlemesi

## API (Gateway altında `/oled_faces/*`)

- `GET /oled_faces/healthz`
- `GET /oled_faces/status`
- `GET /oled_faces/catalog`
- `POST /oled_faces/manual` (`mode`: bitmap|animation|logo)
- `POST /oled_faces/event` (`type`, opsiyonel `data`)
- `POST /oled_faces/stt_text` (speech modülünden beslenir)

## Konfigürasyon

`config/config.yml`:
- `display` I2C ayarları
- `event_map`, `idle_ambient.pool`
- `use_full_catalog: true` ile geniş mood/gesture/activity kataloğu

## İlişkiler

- `expression`: OLED modality
- `autonomy`: dominant duygu yansıması
- `speech`: konuşma sırasında yüz/altyazı senkronu

Robotun "yüz ifadesi" katmanıdır; karar üretmez, semantik durumu görselleştirir.
