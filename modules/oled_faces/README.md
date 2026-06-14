# OLED Faces Module

Robot durum/olay sinyallerini Raspberry Pi SSD1306 OLED ekranda **Pip tarzı prosedürel animasyonlu gözlere** dönüştürür.

## Kaynaklar
- Durum: `state_manager` (`operational`, `emotions`)
- Olaylar: `interactions` event akışı
- Yüz motoru: `services/eyes/` (moods, gestures, activities — esp-bridge-mcp-robot Pip motoru)

## API
- `GET /oled_faces/healthz`
- `GET /oled_faces/status`
- `POST /oled_faces/manual` (`mode`: `bitmap|animation|logo`, `name`)
- `POST /oled_faces/event` (`type`, opsiyonel `data`)

## Not
- OLED sürüşü Pi I2C üzerinden (`display` ayarları: `config/config.yml`).
- Eski Irisoled bitmap/JSON varlıkları kaldırıldı; legacy isimler `services/legacy_map.py` ile Pip motoruna yönlendirilir.
