# Sub-Agent: scheduler-specialist

## Uzmanlık
`Scheduler` ve `scheduler` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/scheduler.md`

## Bileşen haritası
- `Scheduler` — modules/scheduler/services/runner.py

## Dış bağlantılar (neden)
- [[diagnostics]] (http): `scheduler` HTTP ile `diagnostics` modülüne erişir: Sistem sağlık kontrolü çalıştırır.
- [[interactions]] (http): `scheduler` HTTP ile `interactions` modülüne erişir: Sistem olayı veya LED efekti tetikler.
- [[speak]] (http): Zamanlanmış görevlerde hatırlatma/duyuru metni seslendirir.

## Gelen bağlantılar (neden)
- [[gateway]] (import): `gateway` kod içinde `scheduler` modülünü import eder (`config_loader`) — Cron benzeri zamanlayıcı.
- [[gateway]] (import): `gateway` kod içinde `scheduler` modülünü import eder (`services`) — Cron benzeri zamanlayıcı.
- [[gateway]] (import): `gateway` kod içinde `scheduler` modülünü import eder (`api`) — Cron benzeri zamanlayıcı.
