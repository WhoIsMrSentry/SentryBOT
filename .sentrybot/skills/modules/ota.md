# Skill: ota

## Ana bileşen
- Sınıf: `None` in `None`
- Mission: Over-the-air güncelleme, checksum doğrulama

## API özeti
- `GET /healthz` → `healthz()` → clear_versions, scan_once, upload_path, versions
- `POST /scan_once` → `scan_once()` → clear_versions, scan_once, upload_path, versions
- `POST /upload` → `upload()` → clear_versions, upload_path, versions
- `GET /versions` → `versions()` → clear_versions, versions
- `POST /versions/clear` → `clear()` → clear_versions

## Dış ilişkiler (neden)
- → [[logwrapper]] (import): `ota` → `logwrapper`: Merkezi WebSocket log yayınına bağlanır.

## Gelen ilişkiler (neden)
- ← [[gateway]] (import): `gateway` kod içinde `ota` modülünü import eder (`api`) — Over-the-air güncelleme, checksum doğrulama.
- ← [[gateway]] (import): `gateway` kod içinde `ota` modülünü import eder (`config_loader`) — Over-the-air güncelleme, checksum doğrulama.

## Tam bilgi
`.sentrybot/obsidian/modules/ota.md` (10 dosya, 432 satır)
