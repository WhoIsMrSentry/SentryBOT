# Sub-Agent: wakeword-specialist

## Uzmanlık
`WakewordActions` ve `wakeword` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/wakeword.md`

## Bileşen haritası
- `OpenWakewordRunner` — modules/wakeword/services/openwakeword_runner.py
- `WakewordConfig` — modules/wakeword/services/wakeword_detector.py
- `WakewordDetector` — modules/wakeword/services/wakeword_detector.py
- `WakewordActions` — modules/wakeword/xWakewordService.py

## Dış bağlantılar (neden)
- [[arduino_serial]] (registry): Algılama anında buzzer/LED geri bildirimi tetikler.
- [[logwrapper]] (import): `wakeword` → `logwrapper`: Merkezi WebSocket log yayınına bağlanır.
- [[speech]] (import): Wake kelime algılandığında ASR pipeline'ını başlatır.
- [[speech]] (registry): Wake kelime algılandığında ASR pipeline'ını başlatır.

## Gelen bağlantılar (neden)
- [[autonomy]] (http): `autonomy` `wakeword` modülünün HTTP API'sine istek atar (calls path `/wakeword/start`).
- [[autonomy]] (http): `autonomy` `wakeword` modülünün HTTP API'sine istek atar (calls path `/wakeword/stop`).
- [[diagnostics]] (http): `diagnostics` `wakeword` modülünün HTTP API'sine istek atar (calls path `/wakeword/status`).
- [[gateway]] (http): `gateway` `wakeword` modülünün HTTP API'sine istek atar (calls path `/wakeword/status`).
- [[gateway]] (import): `gateway` kod içinde `wakeword` modülünü import eder (`xWakewordService`) — "Hey Sentry" sürekli dinleme (Porcupine/Snowboy).
- [[gateway]] (import): `gateway` kod içinde `wakeword` modülünü import eder (`api`) — "Hey Sentry" sürekli dinleme (Porcupine/Snowboy).
