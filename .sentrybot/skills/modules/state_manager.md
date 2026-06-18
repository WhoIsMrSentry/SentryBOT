# Skill: state_manager

## Ana bileşen
- Sınıf: `None` in `None`
- Mission: Thread-safe global durum deposu, pub/sub

## API özeti
- `GET /healthz` → `healthz()` → —
- `GET /get` → `get_state()` → —
- `POST /set` → `set_state()` → —
- `POST /set/operational` → `set_operational()` → —
- `POST /set/emotions` → `set_emotions()` → —

## Dış ilişkiler (neden)
- —

## Gelen ilişkiler (neden)
- ← [[gateway]] (import): `gateway` kod içinde `state_manager` modülünü import eder (`config_loader`) — Thread-safe global durum deposu, pub/sub.
- ← [[gateway]] (import): `gateway` kod içinde `state_manager` modülünü import eder (`services`) — Thread-safe global durum deposu, pub/sub.
- ← [[gateway]] (import): `gateway` kod içinde `state_manager` modülünü import eder (`api`) — Thread-safe global durum deposu, pub/sub.

## Tam bilgi
`.sentrybot/obsidian/modules/state_manager.md` (11 dosya, 321 satır)
