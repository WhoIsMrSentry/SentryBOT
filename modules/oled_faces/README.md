# OLED Faces Module

Robot durum/olay sinyallerini Raspberry Pi SSD1306 OLED ekranda **Pip tarzı prosedürel animasyonlu gözlere** dönüştürür.

## Kaynaklar
- Durum: `state_manager` (`operational`, `emotions`)
- Olaylar: `interactions` event akışı
- Yüz motoru: `services/eyes/` (moods, gestures, activities — [esp-bridge-mcp-robot](https://github.com/WhoIsMrSentry/esp-bridge-mcp-robot) Pip motoru, senkron: `src/modules/espbridge/eyes/`)

## API
- `GET /oled_faces/healthz`
- `GET /oled_faces/status`
- `POST /oled_faces/manual` (`mode`: `bitmap|animation|logo`, `name`)
- `POST /oled_faces/event` (`type`, opsiyonel `data`)

## Not
- OLED sürüşü Pi I2C üzerinden (`display` ayarları: `config/config.yml`).
- Eski Irisoled bitmap/JSON varlıkları kaldırıldı; legacy isimler `services/legacy_map.py` ile Pip motoruna yönlendirilir.
- `config_loader` açılışta `catalog_registry.expand_config()` ile **31 mood + 24 gesture + 8 activity** motor girdisini `event_map` ve `idle_ambient.pool` içine birleştirir (`use_full_catalog: true`).
