# Admin UI

LAN-only operatör paneli. Gateway altına `/admin` olarak mount edilen vanilla HTML + JS dashboard; çalışan modüllerin anlık görüntülerini REST ve SSE ile birleştirir.

## Sorumluluklar

- Arbiter, mood, IMX500, on-sensor bus durumunu tek ekranda toplama
- Vision, sosyal kişiler, realtime profil, runtime registry, donanım varlık haritası
- Realtime profil değişimini atomik tetikleme (`agent_core` + `vlm_bridge` + `ollama`)
- LAN CIDR allowlist ve opsiyonel `X-Admin-Token`

## Mimari

- Giriş: `xAdminUiService.py` (aggregator shim; kendi FastAPI sürecini başlatmaz)
- Aggregator: `services/dashboard.py` (`DashboardAggregator`)
- Erişim: `services/lan_filter.py`
- Router: `api/router.py` (`mount()`)
- Statik: `static/index.html`, `app.js`, `style.css`

Gateway `_include_admin_ui` varsayılan olarak (`include.admin_ui: true`) `mount()` çağırır. `started` sözlüğünden in-process örnekleri okur; eksik anahtarlar paneli düşürmez.

## API (Gateway altında `/admin/*`)

- `GET /admin/health` — LAN kontrolü + temel durum (token yok)
- `GET /admin/ui`, `/admin/ui/{path}` — statik panel
- `GET /admin/api/status` — arbiter / mood / imx500 / onsensor
- `GET /admin/api/vision` — VLM mod, follow, realtime profil
- `GET /admin/api/people?limit=` — `social_db` kişi listesi (yoksa VLM identity fallback)
- `GET /admin/api/profiles` — aktif realtime profil + subagent limiti
- `GET /admin/api/config` — runtime registry anahtarları
- `GET /admin/api/hardware` — arduino / esp_link / camera / neopixel / imx500
- `GET /admin/api/all` — tüm snapshot'lar
- `POST /admin/api/profile/switch` `{ name }` — profil değişimi
- `GET /admin/api/stream` — SSE (`event: status`)

Token doluysa `auth.header` (varsayılan `X-Admin-Token`) gerekir.

## Konfigürasyon

`config/config.yml`:
- `enabled`, `mount_prefix` (`/admin`)
- `bind_lan_only`, `allowed_networks` (RFC1918 + loopback + link-local)
- `auth.token`, `auth.header`
- `sse.interval_s`, `sse.heartbeat_s`

## İlişkiler

- `gateway`: varsayılan mount
- `agent_core`, `autonomy`, `vlm_bridge`, `social_db`, `config_center`, `state_manager`, `camera`, `arduino_serial`, `esp_link`, `neopixel`, `ollama`

Otonom karar üretmez; operatör gözlem ve profil geçiş yüzüdür.
