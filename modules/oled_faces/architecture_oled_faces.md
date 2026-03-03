# Architecture – OLED Faces

## Amaç
`Irisoled` bitmap/animasyonlarını robotun anlık durumlarına bağlayarak SSD1306 ekranda ifade üretmek.

## Bileşenler
- `xOledFacesService`: servis yaşam döngüsü, state polling, event işleme
- `services/mapper.py`: olay/durum -> bitmap/animasyon eşleme
- `api/router.py`: manuel kontrol ve gözlem endpointleri
- `config/config.yml`: eşleme tabloları

## Veri Akışı
1. Gateway `bootstrap`, `xOledFacesService` örneğini oluşturur.
2. Servis periyodik olarak `state_manager` store'dan state çeker.
3. `interactions` event handler ile olaylar canlı iletilir.
4. `arduino_serial` event handler ile RFID gibi donanım olayları alınır.
5. Servis, `arduino_serial.oled_*` çağrılarıyla firmware'e NDJSON komutu gönderir.

## Tasarım Kararları
- State ve event kaynakları ayrıştırıldı; mapping tek noktada yönetiliyor.
- Bilinmeyen olaylar için deterministic fallback (hash tabanlı bitmap seçimi) kullanılıyor.
- Arduino tarafı `Irisoled` kütüphanesi yoksa degrade modda derlenebilir.

## Genişletme
- `config.yml` üzerinden yeni event/state eşlemeleri eklenebilir.
- Yeni animasyon adları firmware `xOledDisplay` katmanına eklendiğinde doğrudan kullanılabilir.
