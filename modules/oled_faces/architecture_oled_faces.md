# Architecture – OLED Faces

## Amaç
`Irisoled` bitmap/animasyonlarını robotun anlık durumlarına bağlayarak SSD1306 ekranda ifade üretmek.

## Bileşenler
- `xOledFacesService`: servis yaşam döngüsü, state polling, event işleme
- `services/mapper.py`: olay/durum -> bitmap/animasyon eşleme
- `services/pi_ssd1306_driver.py`: Pi I2C SSD1306 sürücüsü (doğrudan render)
- `api/router.py`: manuel kontrol ve gözlem endpointleri
- `config/config.yml`: eşleme tabloları

## Veri Akışı
1. Gateway `bootstrap`, `xOledFacesService` örneğini oluşturur.
2. Servis periyodik olarak `state_manager` store'dan state çeker.
3. `interactions` event handler ile olaylar canlı iletilir.
4. Servis bitmap/animasyon varlıklarını diskten yükler.
5. Render, Raspberry Pi üzerinde SSD1306 I2C hattına doğrudan gönderilir.

## Mermaid Veri Akışı

```mermaid
flowchart TD
	GW[Gateway bootstrap] --> OFS[xOledFacesService start]
	OFS --> SM[StateManager poll]
	OFS --> IE[Interactions event queue]
	OFS --> MP[Mapper resolve face asset]
	MP --> AS[(assets bitmaps and animations)]
	AS --> DRV[PiSSD1306Driver render]
	DRV --> OLED[(SSD1306 I2C screen)]
```

## Mermaid Bileşen İlişkileri

```mermaid
erDiagram
	xOledFacesService ||--|| Mapper : uses
	xOledFacesService ||--|| PiSSD1306Driver : renders_with
	xOledFacesService ||--o{ StateManager : polls
	xOledFacesService ||--o{ Interactions : consumes_events
	Mapper ||--o{ FaceAssets : resolves

	xOledFacesService {
		int poll_interval_ms
		string last_face_key
	}
	Mapper {
		string event_key
		string mapped_asset
	}
	PiSSD1306Driver {
		string i2c_bus
		string device_address
	}
	FaceAssets {
		string asset_name
		string asset_path
	}
```

## Tasarım Kararları
- State ve event kaynakları ayrıştırıldı; mapping tek noktada yönetiliyor.
- Bilinmeyen olaylar için deterministic fallback (hash tabanlı bitmap seçimi) kullanılıyor.
- Arduino OLED transport bağımlılığı kaldırıldı; OLED tek sahipliği Pi tarafında.

## Genişletme
- `config.yml` üzerinden yeni event/state eşlemeleri eklenebilir.
- Yeni animasyon adları `assets/animations/*.json` dosyalarıyla eklenebilir.
