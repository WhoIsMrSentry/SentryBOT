# OLED Faces Config

`config.yml` içindeki eşlemeler robot durumları ve olaylarını SSD1306 yüz bitmap/animasyonlarına dönüştürür.

- `state_map`: state_manager `operational` değerleri için eşleme
- `event_map`: interactions olay adları ve `emotion:*` anahtarları
- `arduino_event_map`: Arduino event akışı için eşleme
- `fallback_unknown`: bilinmeyen durumlarda seçilecek bitmap
