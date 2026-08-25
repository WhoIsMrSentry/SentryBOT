# Perception - Camera

SentryBOT'un ana görüntü yakalama ve yayın modülüdür. PiCamera2 (veya OpenCV/USB fallback) ile kare yakalar, MJPEG yayınlar ve IMX500 on-sensor AI hattına kare sağlar.

## Sorumluluklar

- Canlı MJPEG video akışı (`/camera/video`)
- Tek kare snapshot (`/camera/snap`)
- IMX500/on-sensor algılama verisi sunumu (`/camera/onsensor/*`)
- Takip (tracking) hedef seçimi ve durum raporlama (`/camera/tracking/*`)
- Gateway üzerinden `perception/vision/vlm_bridge` ve diğer görsel modüllere kare kaynağı olma

## Mimari (Güncel: 2026-08-20)

- Giriş noktası: `xCameraService.py`
- **Yakalama**: `services/capture.py` → `CameraCapture`, `CaptureConfig`, `FramePublisher`
- **IMX500**: `services/imx500_runner.py` → `Imx500Runner`, `Imx500Config`
- **On-sensor Bus**: `services/onsensor_bus.py` → `OnSensorBus` (pub/sub)
- **Tracking**: `services/tracking.py` → takip hedef yönetimi
- **Capture Loops**: `services/capture_loops.py` — background capture task
- **Capture Bridge**: `services/capture_bridge.py` — VLM bridge için frame queue
- **Router**: `api/router.py`
- **Config**: `config_loader.py`

MCP graph'ta `CameraCapture` doğrudan gateway bootstrap (`_include_camera`) tarafından başlatılır.

## API (Gateway altında `/camera/*`)

### Stream
- `GET /camera/video` — MJPEG akış (boundary=frame)
- `GET /camera/snap` — tek kare JPEG

### Durum / Kontrol
- `GET /camera/healthz`
- `GET /camera/status` — `{ enabled, running, device, resolution, fps, imx500 }`
- `POST /camera/start` — capture başlat
- `POST /camera/stop` — capture durdur

### On-sensor / Tracking (IMX500)
- `GET /camera/onsensor/latest` — son on-sensor inference sonucu
- `GET /camera/tracking/tracks` — aktif track'ler
- `GET /camera/tracking/target` — seçili hedef
- `POST /camera/tracking/select` — hedef seç (`track_id`)

IMX500 için ayrı config endpoint'i yoktur; imx500 durumu `GET /camera/status` yanıtında bir alan olarak döndürülür.

## Konfigürasyon

Merkezi `config/agent.yaml` → `camera` section + modül-içi `config/config.yml` (merge):

```yaml
enabled: true
picamera2:
  size: { width: 1280, height: 720 }
  format: "RGB888"
  frame_rate: 30
  flip: "none"
imx500:
  enabled: true
  model_path: "/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk"
  labels_path: ""
  confidence: 0.50
  iou: 0.65
  max_detections: 20
  preserve_aspect_ratio: true
  classes_of_interest: []
  tracker:
    iou_threshold: 0.30
    max_missed: 8
  target:
    label: "person"
    strategy: "largest"
```

## İlişkiler (Güncel Modül Yolları)

**Consumer (kare tüketici):**
- `perception/vision/vlm_bridge` → `VisionProcessor` local/hybrid mode için `CameraCapture` + `OnSensorBus` subscriber
- `autonomy` → vision context bridge için on-sensor results
- `agent_core/tools/vision_tools.py` → frame capture, status

**Provider (kare üretici):**
- `CameraCapture` → `FramePublisher` (pub/sub)
- `Imx500Runner` → `OnSensorBus` publisher
- `capture_bridge.py` → VLM bridge için async frame queue

**Platform:**
- `platform/telemetry` → camera metrics (fps, latency)
- `platform/diagnostics` → `/camera/healthz` check
- `platform/config_center` → runtime config apply (imx500 enabled, resolution)

## Processing Modları (VLM Bridge ile Koordineli)

| Mod | Açıklama | Camera Role |
|-----|----------|-------------|
| `local` | Pi'de OpenCV face detect/track | `CameraCapture` + `FramePublisher` (CPU) |
| `remote` | PC'ye stream, PC VLM işler | `CameraCapture` stream only (MJPEG) |
| `onsensor` | IMX500 hardware accelerator | `Imx500Runner` + `OnSensorBus` (NPU) |
| `hybrid` | Local capture + remote VLM | `CameraCapture` + `capture_bridge` queue |

`config/robot_execution_profiles.json` → `vision.processing_mode` + `vision.hybrid_local_capture` ile kontrol.

## Bilinen Sorunlar (KRİTİK)

1. **Device Lock / Mode Switching Yok** - `CameraCapture` (PiCamera2) VE `Imx500Runner` **aynı `/dev/video0`**'ı açmaya çalışıyor. `hybrid_local_capture: true` + `mode: local` ikisi de aktifse → **device busy crash**. **`modules/camera/device_manager.py` (YENİ GEREKLİ)** singleton device lock + reference count + mode switching merkezi olmalı.

2. **Capture Bridge Duplicate Logic** - `services/capture_bridge.py` + `services/capture_loops.py` + `services/capture.py` frame publishing logic'i **3 yerde tekrar ediyor**. Tek `FrameSource` abstraction ile birleştirilmeli.

3. **IMX500 Runner Config Drift** - `Imx500Runner` config `Imx500Config` dataclass ama `config_loader.py` merge sonrası dict. Type safety yok. `pydantic` model ile validation.

4. **Healthz Device Check Eksik** - `/camera/healthz` device açık mı kontrol etmiyor, sadece service running döndürüyor.

4. **USB Camera Fallback Test Edilmemiş** - `picamera2` import fail olursa OpenCV `VideoCapture` fallback var ama CI/CD'de test yok.

5. **Resolution/FPS Change Runtime** - `POST /camera/config` yok, capture restart gerekiyor. Dynamic reconfig desteği eklenmeli.