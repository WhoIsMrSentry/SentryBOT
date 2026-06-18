# Skill: calibration

## Ana bileşen
- Sınıf: `None` in `modules/calibration/xCalibrationService.py`
- Mission: Servo kalibrasyon modu

## API özeti
- `GET /healthz` → `healthz()` → —
- `GET /camera/checkerboard` → `checker()` → —
- `GET /servo/sweep` → `servo_sweep()` → —

## Dış ilişkiler (neden)
- → [[arduino_serial]] (registry): Servo kalibrasyon komutlarını Arduino'ya gönderir.
- → [[camera]] (http): `calibration` HTTP ile `camera` modülüne erişir: Kamera stream veya snapshot ister.

## Gelen ilişkiler (neden)
- ← [[gateway]] (import): `gateway` kod içinde `calibration` modülünü import eder (`api`) — Servo kalibrasyon modu.
- ← [[gateway]] (import): `gateway` kod içinde `calibration` modülünü import eder (`config_loader`) — Servo kalibrasyon modu.

## Tam bilgi
`.sentrybot/obsidian/modules/calibration.md` (12 dosya, 152 satır)
