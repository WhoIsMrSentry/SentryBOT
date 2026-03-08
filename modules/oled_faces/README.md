# OLED Faces Module

Bu modül, robotun canlılık/duygu/durum sinyallerini Raspberry Pi üzerinde doğrudan I2C SSD1306 OLED ekrana yüz ifadelerine dönüştürür.

## Kaynaklar
- Durum: `state_manager` (`operational`, `emotions`)
- Olaylar: `interactions` event akışı
- Varlıklar: `assets/bitmaps/*.bin` ve `assets/animations/*.json`

## API
- `GET /oled_faces/healthz`
- `GET /oled_faces/status`
- `POST /oled_faces/manual` (`mode`: `bitmap|animation|logo`, `name`)
- `POST /oled_faces/event` (`type`, opsiyonel `data`)

## Not
- OLED sürüşü Pi tarafındadır (`display` ayarları: `modules/oled_faces/config/config.yml`).
- Arduino firmware'de `cmd: "oled"` komutu artık kullanılmaz.
- Arduino tarafındaki String azaltma optimizasyonları OLED yolunu etkilemez; `oled_faces` API sözleşmesi sabittir.
