# Skill: logwrapper

## Ana bileşen
- Sınıf: `LevelChange` in `modules/logwrapper/api/router.py`
- Mission: WebSocket log yayını, merkezi loglama

## API özeti
- `GET /` → `list_logs()` → —
- `POST /level` → `set_level()` → —

## Dış ilişkiler (neden)
- → [[arduino_serial]] (http): `logwrapper` HTTP ile `arduino_serial` modülüne erişir: Arduino'ya NDJSON komut gönderir veya ACK bekler.
- → [[arduino_serial]] (http): `logwrapper` HTTP ile `arduino_serial` modülüne erişir: Arduino'ya NDJSON komut gönderir veya ACK bekler.
- → [[interactions]] (http): `logwrapper` HTTP ile `interactions` modülüne erişir: Sistem olayı veya LED efekti tetikler.
- → [[interactions]] (http): `logwrapper` HTTP ile `interactions` modülüne erişir: Sistem olayı veya LED efekti tetikler.
- → [[neopixel]] (http): `logwrapper` HTTP ile `neopixel` modülüne erişir: YAML tabanlı servo animasyonu başlatır.
- → [[speech]] (http): `logwrapper` HTTP ile `speech` modülüne erişir: Ses tanıma (ASR) pipeline'ına istek gönderir.
- → [[speech]] (http): `logwrapper` HTTP ile `speech` modülüne erişir: Ses tanıma (ASR) pipeline'ına istek gönderir.
- → [[vlm_bridge]] (http): `logwrapper` gateway veya doğrudan HTTP ile `vlm_bridge` API'sini çağırır (calls path `/vlm/results/latest`).

## Gelen ilişkiler (neden)
- ← [[agent_core]] (import): `agent_core` `logwrapper` modülünden `init_logging` kullanır: Merkezi WebSocket log yayınına bağlanır.
- ← [[camera]] (import): `camera` `logwrapper` modülünden `init_logging` kullanır: Merkezi WebSocket log yayınına bağlanır.
- ← [[gateway]] (import): `gateway` kod içinde `logwrapper` modülünü import eder (`get_router`) — WebSocket log yayını, merkezi loglama.
- ← [[gateway]] (import): `gateway` `logwrapper` modülünden `init_logging` kullanır: Merkezi WebSocket log yayınına bağlanır.
- ← [[hardware]] (import): `hardware` `logwrapper` modülünden `init_logging` kullanır: Merkezi WebSocket log yayınına bağlanır.
- ← [[mutagen]] (import): Senkronizasyon loglarını merkezi log sistemine yazar.
- ← [[neopixel]] (import): `neopixel` `logwrapper` modülünden `init_logging` kullanır: Merkezi WebSocket log yayınına bağlanır.
- ← [[ollama]] (import): `ollama` `logwrapper` modülünden `init_logging` kullanır: Merkezi WebSocket log yayınına bağlanır.
- ← [[ota]] (import): `ota` `logwrapper` modülünden `init_logging` kullanır: Merkezi WebSocket log yayınına bağlanır.
- ← [[piservo]] (import): `piservo` `logwrapper` modülünden `init_logging` kullanır: Merkezi WebSocket log yayınına bağlanır.

## Tam bilgi
`.sentrybot/obsidian/modules/logwrapper.md` (12 dosya, 576 satır)
