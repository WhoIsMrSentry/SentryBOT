# Camera

SentryBOT'un ana görüntü yakalama ve yayın modülüdür. PiCamera2 (veya OpenCV/USB fallback) ile kare yakalar, MJPEG yayınlar ve IMX500 on-sensor AI hattına kare sağlar.

## Sorumluluklar

- Canlı MJPEG video akışı
- Tek kare snapshot
- IMX500/on-sensor algılama verisi sunumu
- Takip (tracking) hedef seçimi ve durum raporlama
- Gateway üzerinden `vlm_bridge` ve diğer görsel modüllere kaynak olma

## Mimari

- Giriş noktası: `xCameraService.py`
- Yakalama: `services/capture.py` (`CameraCapture`, `FramePublisher`)
- IMX500: `services/imx500_runner.py`
- Router: `api/router.py`

MCP graph'ta `CameraCapture` doğrudan gateway bootstrap (`_include_camera`) tarafından başlatılır.

## API (Gateway altında `/camera/*`)

### Stream
- `GET /camera/video` — MJPEG akış
- `GET /camera/snap` — tek kare JPEG

### Durum
- `GET /camera/healthz`
- `GET /camera/status`
- `POST /camera/start`
- `POST /camera/stop`

### On-sensor / Tracking
- `GET /camera/onsensor/latest`
- `GET /camera/tracking/tracks`
- `GET /camera/tracking/target`
- `POST /camera/tracking/select`

## Konfigürasyon

Modül-içi `config/config.yml`:
- `enabled`
- çözünürlük, `fps`, cihaz yolları
- IMX500/on-sensor seçenekleri

## İlişkiler

- `vlm_bridge`: local/hybrid görüntü işleme için kare kaynağı
- `gateway`: kamera gating ve mount
- Otonom davranış için doğrudan karar üretmez; algı katmanının donanım girişidir
