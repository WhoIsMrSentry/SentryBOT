# Skill: animate

## Ana bileşen
- Sınıf: `xAnimateService` in `modules/animate/xAnimateService.py`
- Mission: YAML servo animasyon oynatıcı

## API özeti
- `GET /list` → `list_animations()` → list, run, stop_run
- `POST /run` → `run()` → run, stop_run
- `POST /stop` → `stop()` → stop_run

## Dış ilişkiler (neden)
- → [[arduino_serial]] (arduino): YAML animasyon adımlarını set_pose komutlarına çevirir.
- → [[arduino_serial]] (import): YAML animasyon adımlarını set_pose komutlarına çevirir.
- → [[arduino_serial]] (import): YAML animasyon adımlarını set_pose komutlarına çevirir.
- → [[arduino_serial]] (registry): YAML animasyon adımlarını set_pose komutlarına çevirir.

## Gelen ilişkiler (neden)
- ← [[autonomy]] (http): Duygu durumuna göre vücut animasyonu (stretch, sit, look_around) tetikler.
- ← [[gateway]] (http): `gateway` → `animate`: YAML tabanlı servo animasyonu başlatır.
- ← [[gateway]] (import): `gateway` kod içinde `animate` modülünü import eder (`xAnimateService`) — YAML servo animasyon oynatıcı.
- ← [[gateway]] (import): `gateway` kod içinde `animate` modülünü import eder (`api`) — YAML servo animasyon oynatıcı.
- ← [[interactions]] (http): Sistem olaylarında veya kural tetiklerinde robot hareketi başlatır.
- ← [[neopixel]] (http): LED efektleri ile senkronize fiziksel hareket üretir.
- ← [[neopixel]] (http): LED efektleri ile senkronize fiziksel hareket üretir.

## Tam bilgi
`.sentrybot/obsidian/modules/animate.md` (16 dosya, 476 satır)
