# Skill: mutagen

## Ana bileşen
- Sınıf: `None` in `modules/mutagen/xMutagenService.py`
- Mission: PC↔Pi dosya senkronizasyonu

## API özeti
- `GET /healthz` → `healthz()` → —
- `GET /status` → `status()` → —
- `POST /start` → `start()` → —
- `POST /stop` → `stop()` → —
- `POST /rescan` → `rescan()` → —

## Dış ilişkiler (neden)
- → [[logwrapper]] (import): Senkronizasyon loglarını merkezi log sistemine yazar.

## Gelen ilişkiler (neden)
- ← [[gateway]] (import): `gateway` kod içinde `mutagen` modülünü import eder (`api`) — PC↔Pi dosya senkronizasyonu.
- ← [[gateway]] (import): `gateway` kod içinde `mutagen` modülünü import eder (`config_loader`) — PC↔Pi dosya senkronizasyonu.

## Tam bilgi
`.sentrybot/obsidian/modules/mutagen.md` (10 dosya, 254 satır)
