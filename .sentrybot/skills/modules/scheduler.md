# Skill: scheduler

## Ana bileşen
- Sınıf: `Scheduler` in `modules/scheduler/xSchedulerService.py`
- Mission: Cron benzeri zamanlayıcı

## API özeti
- `GET /healthz` → `healthz()` → —
- `GET /jobs` → `jobs()` → —
- `POST /jobs` → `add_or_update_job()` → —
- `DELETE /jobs/{job_id}` → `remove_job()` → —
- `GET /results` → `results()` → —
- `POST /run_once/{job_id}` → `run_once()` → —

## Dış ilişkiler (neden)
- → [[diagnostics]] (http): `scheduler` HTTP ile `diagnostics` modülüne erişir: Sistem sağlık kontrolü çalıştırır.
- → [[interactions]] (http): `scheduler` HTTP ile `interactions` modülüne erişir: Sistem olayı veya LED efekti tetikler.
- → [[speak]] (http): Zamanlanmış görevlerde hatırlatma/duyuru metni seslendirir.

## Gelen ilişkiler (neden)
- ← [[gateway]] (import): `gateway` kod içinde `scheduler` modülünü import eder (`config_loader`) — Cron benzeri zamanlayıcı.
- ← [[gateway]] (import): `gateway` kod içinde `scheduler` modülünü import eder (`services`) — Cron benzeri zamanlayıcı.
- ← [[gateway]] (import): `gateway` kod içinde `scheduler` modülünü import eder (`api`) — Cron benzeri zamanlayıcı.

## Tam bilgi
`.sentrybot/obsidian/modules/scheduler.md` (11 dosya, 371 satır)
