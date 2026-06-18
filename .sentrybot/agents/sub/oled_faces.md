# Sub-Agent: oled_faces-specialist

## Uzmanlık
`xOledFacesService` ve `oled_faces` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/oled_faces.md`

## Bileşen haritası
- `EyeEngine` — modules/oled_faces/services/eyes/engine.py
- `FaceCoordinator` — modules/oled_faces/services/face_coordinator.py
- `FaceDecision` — modules/oled_faces/services/face_coordinator.py
- `FaceRenderer` — modules/oled_faces/services/face_renderer.py
- `IdleAmbientPlayer` — modules/oled_faces/services/idle_ambient.py
- `FaceCommand` — modules/oled_faces/services/legacy_map.py
- `FaceMapper` — modules/oled_faces/services/mapper.py
- `OledAction` — modules/oled_faces/services/mapper.py
- `PiSsd1306Driver` — SSD1306 I2C driver for Raspberry Pi; accepts PIL frames from the eye engine.
- `xOledFacesService` — modules/oled_faces/xOledFacesService.py

## Dış bağlantılar (neden)
- [[common]] (import): Yüz ifadesi ve duygu taksonomisini ortak sözlükten alır.

## Gelen bağlantılar (neden)
- [[gateway]] (import): `gateway` kod içinde `oled_faces` modülünü import eder (`xOledFacesService`) — OLED ekran yüz ifadeleri.
- [[gateway]] (import): `gateway` kod içinde `oled_faces` modülünü import eder (`api`) — OLED ekran yüz ifadeleri.
