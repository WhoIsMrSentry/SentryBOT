# Skill: wakeword

## Ana bileşen
- Sınıf: `WakewordActions` in `modules/wakeword/xWakewordService.py`
- Mission: "Hey Sentry" sürekli dinleme (Porcupine/Snowboy)

## API özeti
- `GET /wakeword/healthz` → `healthz()` → start_background, status, stop
- `GET /wakeword/status` → `status()` → start_background, status, stop
- `POST /wakeword/start` → `start()` → start_background, stop
- `POST /wakeword/stop` → `stop()` → stop

## Dış ilişkiler (neden)
- → [[arduino_serial]] (registry): Algılama anında buzzer/LED geri bildirimi tetikler.
- → [[logwrapper]] (import): `wakeword` → `logwrapper`: Merkezi WebSocket log yayınına bağlanır.
- → [[speech]] (import): Wake kelime algılandığında ASR pipeline'ını başlatır.
- → [[speech]] (registry): Wake kelime algılandığında ASR pipeline'ını başlatır.

## Gelen ilişkiler (neden)
- ← [[autonomy]] (http): `autonomy` `wakeword` modülünün HTTP API'sine istek atar (calls path `/wakeword/start`).
- ← [[autonomy]] (http): `autonomy` `wakeword` modülünün HTTP API'sine istek atar (calls path `/wakeword/stop`).
- ← [[diagnostics]] (http): `diagnostics` `wakeword` modülünün HTTP API'sine istek atar (calls path `/wakeword/status`).
- ← [[gateway]] (http): `gateway` `wakeword` modülünün HTTP API'sine istek atar (calls path `/wakeword/status`).
- ← [[gateway]] (import): `gateway` kod içinde `wakeword` modülünü import eder (`xWakewordService`) — "Hey Sentry" sürekli dinleme (Porcupine/Snowboy).
- ← [[gateway]] (import): `gateway` kod içinde `wakeword` modülünü import eder (`api`) — "Hey Sentry" sürekli dinleme (Porcupine/Snowboy).

## Tam bilgi
`.sentrybot/obsidian/modules/wakeword.md` (13 dosya, 1021 satır)
