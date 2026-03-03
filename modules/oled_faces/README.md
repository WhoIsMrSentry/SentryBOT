# OLED Faces Module

Bu modül, robotun canlılık/duygu/durum sinyallerini Arduino SSD1306 OLED ekranında yüz ifadelerine dönüştürür.

## Kaynaklar
- Durum: `state_manager` (`operational`, `emotions`)
- Olaylar: `interactions` event akışı
- Donanım eventleri: `arduino_serial` event handler

## API
- `GET /oled_faces/healthz`
- `GET /oled_faces/status`
- `POST /oled_faces/manual` (`mode`: `bitmap|animation|logo`, `name`)
- `POST /oled_faces/event` (`type`, opsiyonel `data`)

## Not
Arduino firmware tarafında `cmd: "oled"` komutu desteklenmelidir.
