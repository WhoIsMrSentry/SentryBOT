# Sub-Agent: camera-specialist

## Uzmanlık
`CameraCapture` ve `camera` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/camera.md`

## Bileşen haritası
- `CameraCapture` — modules/camera/services/capture.py
- `CaptureConfig` — modules/camera/services/capture.py
- `FramePublisher` — modules/camera/services/capture.py
- `Imx500Config` — modules/camera/services/imx500_runner.py
- `Imx500Runner` — Manages the IMX500 inference loop and publishes detections to the bus.
- `OnSensorDetection` — Single bounding-box detection emitted by the IMX500 sensor.
- `OnSensorEventBus` — Tiny publish/subscribe broker that retains the latest snapshot.
- `OnSensorSnapshot` — A snapshot of detections emitted by the IMX500 backend.

## Dış bağlantılar (neden)
- [[logwrapper]] (import): `camera` → `logwrapper`: Merkezi WebSocket log yayınına bağlanır.

## Gelen bağlantılar (neden)
- [[calibration]] (http): `calibration` → `camera`: Kamera stream veya snapshot ister.
- [[calibration]] (http): `calibration` → `camera`: Kamera stream veya snapshot ister.
- [[common]] (http): `common` → `camera`: Kamera stream veya snapshot ister.
- [[diagnostics]] (http): Kamera erişim ve stream testi yapar.
- [[diagnostics]] (registry): Kamera erişim ve stream testi yapar.
- [[gateway]] (http): `gateway` → `camera`: Kamera stream veya snapshot ister.
- [[gateway]] (http): `gateway` → `camera`: Kamera stream veya snapshot ister.
- [[gateway]] (import): `gateway` kod içinde `camera` modülünü import eder (`config_loader`) — MJPEG kamera stream, auto-recovery.
- [[gateway]] (import): `gateway` kod içinde `camera` modülünü import eder (`services`) — MJPEG kamera stream, auto-recovery.
- [[gateway]] (import): `gateway` kod içinde `camera` modülünü import eder (`api`) — MJPEG kamera stream, auto-recovery.
- [[vlm_bridge]] (http): MJPEG/frame kaynağı olarak kamera stream'ini kullanır.
- [[vlm_bridge]] (http): MJPEG/frame kaynağı olarak kamera stream'ini kullanır.
