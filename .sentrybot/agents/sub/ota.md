# Sub-Agent: ota-specialist

## Uzmanlık
`None` ve `ota` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/ota.md`

## Bileşen haritası
- `AvrDudeUploader` — modules/ota/services/uploader.py
- `OTAService` — modules/ota/services/uploader.py

## Dış bağlantılar (neden)
- [[logwrapper]] (import): `ota` → `logwrapper`: Merkezi WebSocket log yayınına bağlanır.

## Gelen bağlantılar (neden)
- [[gateway]] (import): `gateway` kod içinde `ota` modülünü import eder (`api`) — Over-the-air güncelleme, checksum doğrulama.
- [[gateway]] (import): `gateway` kod içinde `ota` modülünü import eder (`config_loader`) — Over-the-air güncelleme, checksum doğrulama.
