# Sub-Agent: admin_ui-specialist

## Uzmanlık
`xAdminUiService` ve `admin_ui` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/admin_ui.md`

## Bileşen haritası
- `DashboardAggregator` — modules/admin_ui/services/dashboard.py
- `xAdminUiService` — modules/admin_ui/xAdminUiService.py

## Dış bağlantılar (neden)
- [[gateway]] (registry): Tek port üzerinden tüm modül API'lerine erişir.

## Gelen bağlantılar (neden)
- [[gateway]] (import): `gateway` kod içinde `admin_ui` modülünü import eder (`api`) — Web yönetim paneli (statik dosyalar).
- [[gateway]] (import): `gateway` kod içinde `admin_ui` modülünü import eder (`config_loader`) — Web yönetim paneli (statik dosyalar).
