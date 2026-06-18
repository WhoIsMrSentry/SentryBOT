# Sub-Agent: logwrapper-specialist

## Uzmanlık
`LevelChange` ve `logwrapper` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/logwrapper.md`

## Bileşen haritası
- `LevelChange` — modules/logwrapper/api/router.py
- `InMemoryLogHandler` — Basit halka buffer log handler.

## Dış bağlantılar (neden)
- [[arduino_serial]] (http): `logwrapper` HTTP ile `arduino_serial` modülüne erişir: Arduino'ya NDJSON komut gönderir veya ACK bekler.
- [[arduino_serial]] (http): `logwrapper` HTTP ile `arduino_serial` modülüne erişir: Arduino'ya NDJSON komut gönderir veya ACK bekler.
- [[interactions]] (http): `logwrapper` HTTP ile `interactions` modülüne erişir: Sistem olayı veya LED efekti tetikler.
- [[interactions]] (http): `logwrapper` HTTP ile `interactions` modülüne erişir: Sistem olayı veya LED efekti tetikler.
- [[neopixel]] (http): `logwrapper` HTTP ile `neopixel` modülüne erişir: YAML tabanlı servo animasyonu başlatır.
- [[speech]] (http): `logwrapper` HTTP ile `speech` modülüne erişir: Ses tanıma (ASR) pipeline'ına istek gönderir.
- [[speech]] (http): `logwrapper` HTTP ile `speech` modülüne erişir: Ses tanıma (ASR) pipeline'ına istek gönderir.
- [[vlm_bridge]] (http): `logwrapper` gateway veya doğrudan HTTP ile `vlm_bridge` API'sini çağırır (calls path `/vlm/results/latest`).

## Gelen bağlantılar (neden)
- [[agent_core]] (import): `agent_core` `logwrapper` modülünden `init_logging` kullanır: Merkezi WebSocket log yayınına bağlanır.
- [[camera]] (import): `camera` `logwrapper` modülünden `init_logging` kullanır: Merkezi WebSocket log yayınına bağlanır.
- [[gateway]] (import): `gateway` kod içinde `logwrapper` modülünü import eder (`get_router`) — WebSocket log yayını, merkezi loglama.
- [[gateway]] (import): `gateway` `logwrapper` modülünden `init_logging` kullanır: Merkezi WebSocket log yayınına bağlanır.
- [[hardware]] (import): `hardware` `logwrapper` modülünden `init_logging` kullanır: Merkezi WebSocket log yayınına bağlanır.
- [[mutagen]] (import): Senkronizasyon loglarını merkezi log sistemine yazar.
- [[neopixel]] (import): `neopixel` `logwrapper` modülünden `init_logging` kullanır: Merkezi WebSocket log yayınına bağlanır.
- [[ollama]] (import): `ollama` `logwrapper` modülünden `init_logging` kullanır: Merkezi WebSocket log yayınına bağlanır.
- [[ota]] (import): `ota` `logwrapper` modülünden `init_logging` kullanır: Merkezi WebSocket log yayınına bağlanır.
- [[piservo]] (import): `piservo` `logwrapper` modülünden `init_logging` kullanır: Merkezi WebSocket log yayınına bağlanır.
- [[speak]] (import): `speak` `logwrapper` modülünden `init_logging` kullanır: Merkezi WebSocket log yayınına bağlanır.
- [[speech]] (import): `speech` `logwrapper` modülünden `init_logging` kullanır: Merkezi WebSocket log yayınına bağlanır.
