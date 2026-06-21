# Skill: camera

## Ana bileşen
- Sınıf: `CameraCapture` in `modules/camera/xCameraService.py`
- Mission: MJPEG kamera stream, auto-recovery

## API özeti
- `GET /video` → `video_stream()` → —
- `GET /snap` → `snapshot()` → —
- `GET /healthz` → `healthz()` → —
- `POST /start` → `start_camera()` → —
- `POST /stop` → `stop_camera()` → —

## Dış ilişkiler (neden)
- → [[logwrapper]] (import): `camera` → `logwrapper`: Merkezi WebSocket log yayınına bağlanır.

## Gelen ilişkiler (neden)
- ← [[calibration]] (http): `calibration` → `camera`: Kamera stream veya snapshot ister.
- ← [[calibration]] (http): `calibration` → `camera`: Kamera stream veya snapshot ister.
- ← [[common]] (http): `common` → `camera`: Kamera stream veya snapshot ister.
- ← [[diagnostics]] (http): Kamera erişim ve stream testi yapar.
- ← [[diagnostics]] (registry): Kamera erişim ve stream testi yapar.
- ← [[gateway]] (http): `gateway` → `camera`: Kamera stream veya snapshot ister.
- ← [[gateway]] (http): `gateway` → `camera`: Kamera stream veya snapshot ister.
- ← [[gateway]] (import): `gateway` kod içinde `camera` modülünü import eder (`config_loader`) — MJPEG kamera stream, auto-recovery.
- ← [[gateway]] (import): `gateway` kod içinde `camera` modülünü import eder (`services`) — MJPEG kamera stream, auto-recovery.
- ← [[gateway]] (import): `gateway` kod içinde `camera` modülünü import eder (`api`) — MJPEG kamera stream, auto-recovery.

## Tam bilgi
`.sentrybot/obsidian/modules/camera.md` (17 dosya, 1425 satır)
