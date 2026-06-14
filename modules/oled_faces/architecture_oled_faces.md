# Architecture – OLED Faces

## Amaç
Robotun anlık durum ve olaylarını SSD1306 ekranda **prosedürel animasyonlu göz ifadelerine** dönüştürmek (Pip `EyeEngine`).

## Bileşenler
- `xOledFacesService`: servis yaşam döngüsü, state polling, event işleme
- `services/mapper.py`: olay/durum -> mode/name eşleme
- `services/legacy_map.py`: eski Irisoled isimlerini Pip mood/gesture/activity'ye çevirir
- `services/face_renderer.py`: `EyeEngine` + `PiSsd1306Driver` birleşimi
- `services/eyes/`: Pip yüz katmanları (`moods`, `gestures`, `activities`, `engine`)
- `services/pi_ssd1306_driver.py`: Pi I2C SSD1306 sürücüsü
- `api/router.py`: manuel kontrol ve gözlem endpointleri
- `config/config.yml`: eşleme tabloları

## Veri Akışı
1. Gateway `bootstrap`, `xOledFacesService` örneğini oluşturur.
2. Servis periyodik olarak `state_manager` store'dan state çeker.
3. `interactions` event handler ile olaylar canlı iletilir.
4. `FaceMapper` mode/name üretir; `FaceRenderer` Pip motoruna uygular.
5. `EyeEngine` PIL ile kare üretir; `PiSsd1306Driver` I2C'ye yazar.

## Tasarım Kararları
- State ve event kaynakları ayrıştırıldı; mapping tek noktada yönetiliyor.
- Irisoled bitmap bağımlılığı kaldırıldı; tüm yüzler prosedürel.
- Legacy config isimleri (`normal`, `scan`, `blink`, …) `legacy_map` ile korunur.

## Genişletme
- Yeni mood/gesture/activity: `services/eyes/` altındaki ilgili dosyaya tek satır ekle.
- Yeni event/state eşlemesi: `config.yml` `state_map` / `event_map`.
- Eski isim alias: `services/legacy_map.py`.
