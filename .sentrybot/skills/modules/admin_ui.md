# Skill: admin_ui

## Ana bileşen
- Sınıf: `xAdminUiService` in `modules/admin_ui/xAdminUiService.py`
- Mission: Web yönetim paneli (statik dosyalar)

## API özeti
- `GET /health` → `health()` → —
- `GET /ui` → `ui_index()` → —
- `GET /ui/{path:path}` → `ui_asset()` → —
- `GET /api/status` → `api_status()` → —
- `GET /api/vision` → `api_vision()` → —
- `GET /api/people` → `api_people()` → —
- `GET /api/profiles` → `api_profiles()` → —
- `GET /api/config` → `api_config()` → —
- `GET /api/hardware` → `api_hardware()` → —
- `GET /api/all` → `api_all()` → —

## Dış ilişkiler (neden)
- → [[gateway]] (registry): Tek port üzerinden tüm modül API'lerine erişir.

## Gelen ilişkiler (neden)
- ← [[gateway]] (import): `gateway` kod içinde `admin_ui` modülünü import eder (`api`) — Web yönetim paneli (statik dosyalar).
- ← [[gateway]] (import): `gateway` kod içinde `admin_ui` modülünü import eder (`config_loader`) — Web yönetim paneli (statik dosyalar).

## Tam bilgi
`.sentrybot/obsidian/modules/admin_ui.md` (13 dosya, 1023 satır)
