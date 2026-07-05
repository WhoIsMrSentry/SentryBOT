# Sub-Agent: state_manager-specialist

## Uzmanlık
`None` ve `state_manager` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/state_manager.md`

## Bileşen haritası
- `StateStore` — modules/state_manager/services/store.py

## Dış bağlantılar (neden)
- —

## Gelen bağlantılar (neden)
- [[gateway]] (import): `gateway` kod içinde `state_manager` modülünü import eder (`config_loader`) — Thread-safe global durum deposu, pub/sub.
- [[gateway]] (import): `gateway` kod içinde `state_manager` modülünü import eder (`services`) — Thread-safe global durum deposu, pub/sub.
- [[gateway]] (import): `gateway` kod içinde `state_manager` modülünü import eder (`api`) — Thread-safe global durum deposu, pub/sub.
