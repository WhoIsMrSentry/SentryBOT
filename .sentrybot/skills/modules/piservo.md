# Skill: piservo

## Ana bileşen
- Sınıf: `None` in `None`
- Mission: Raspberry Pi GPIO PWM kulak servoları

## API özeti
- `GET /healthz` → `healthz()` → —
- `POST /set` → `set_angles()` → —
- `POST /emotion` → `emotion()` → —
- `POST /gesture` → `gesture()` → —
- `POST /event` → `event()` → —

## Dış ilişkiler (neden)
- → [[arduino_serial]] (arduino): Kulak servo komutları için seri haberleşme (bazı kurulumlarda).
- → [[arduino_serial]] (import): Kulak servo komutları için seri haberleşme (bazı kurulumlarda).
- → [[common]] (import): Kulak pozisyonları duygu sözlüğü ile eşlenir.
- → [[logwrapper]] (import): `piservo` → `logwrapper`: Merkezi WebSocket log yayınına bağlanır.

## Gelen ilişkiler (neden)
- ← [[gateway]] (import): `gateway` kod içinde `piservo` modülünü import eder (`config_loader`) — Raspberry Pi GPIO PWM kulak servoları.
- ← [[gateway]] (import): `gateway` kod içinde `piservo` modülünü import eder (`api`) — Raspberry Pi GPIO PWM kulak servoları.
- ← [[gateway]] (import): `gateway` kod içinde `piservo` modülünü import eder (`services`) — Raspberry Pi GPIO PWM kulak servoları.

## Tam bilgi
`.sentrybot/obsidian/modules/piservo.md` (14 dosya, 462 satır)
