# Skill: oled_faces

## Ana bileşen
- Sınıf: `xOledFacesService` in `modules/oled_faces/xOledFacesService.py`
- Mission: OLED ekran yüz ifadeleri

## API özeti
- `GET /healthz` → `healthz()` → apply_manual, on_interaction_event, status
- `GET /status` → `status()` → apply_manual, on_interaction_event, status
- `POST /manual` → `manual()` → apply_manual, on_interaction_event
- `POST /event` → `push_event()` → on_interaction_event

## Dış ilişkiler (neden)
- → [[common]] (import): Yüz ifadesi ve duygu taksonomisini ortak sözlükten alır.

## Gelen ilişkiler (neden)
- ← [[gateway]] (import): `gateway` kod içinde `oled_faces` modülünü import eder (`xOledFacesService`) — OLED ekran yüz ifadeleri.
- ← [[gateway]] (import): `gateway` kod içinde `oled_faces` modülünü import eder (`api`) — OLED ekran yüz ifadeleri.

## Tam bilgi
`.sentrybot/obsidian/modules/oled_faces.md` (31 dosya, 2496 satır)
