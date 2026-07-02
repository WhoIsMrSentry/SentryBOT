# Admin UI

LAN-only tek yönetim paneli. `/admin/*` altında sunulan, arbiter/vision/sosyal durum anlık görüntülerini birleştiren vanilla HTML + JS dashboard ve destekleyici REST/SSE uç noktaları.

## Ne İşe Yarar?
- Diğer modüllerin (agent_core, vlm_bridge, social_db, config_center, donanım) canlı durumunu tek ekranda toplar.
- LAN allowlist (CIDR) ve opsiyonel token ile erişimi kısıtlar.
- SSE üzerinden periyodik durum anlık görüntüsü yayınlar.
- Realtime profil değişimini (agent_core + vlm_bridge + ollama) tek uçtan tetikler.

## Bağımsız Çalıştırma
Admin UI kendi başına bir FastAPI uygulaması **başlatmaz**; gateway (veya herhangi bir host FastAPI app) üzerine `mount()` ile takılır:

```python
from fastapi import FastAPI
from modules.admin_ui.api.router import mount
from modules.admin_ui.config_loader import load_config

app = FastAPI()
started = {"gateway_base_url": "http://127.0.0.1:8080", ...}
mount(app, load_config(None), started)
```

`started` sözlüğü, panelin veri okuduğu çalışan modül örneklerini (`agent_core`, `vlm_bridge`, `social_db`, `runtime_registry`, `state_manager`, `imx500_runner`, `onsensor_bus`, `arduino`, `esp_link`, `camera`, `neopixel`, `autonomy`) içerir; eksik anahtarlar `DashboardAggregator` tarafından güvenli biçimde `None`/boş olarak ele alınır, tek bir alt sistemin çökmesi paneli etkilemez.

Test veya bağımsız deneme için, `xAdminUiService` sınıfı `started` sözlüğünü sarmalayıp `snapshot()` üzerinden aynı veriyi kod içinden almayı sağlar (router olmadan).

## API
- GET `/admin/health` — LAN kontrolü + temel durum
- GET `/admin/ui` ve `/admin/ui/{path}` — statik HTML/JS/CSS panel dosyaları
- GET `/admin/api/status` — arbiter/mood/imx500/onsensor bus özeti (token gerekebilir)
- GET `/admin/api/vision` — VLM bridge işleme modu ve takip durumu
- GET `/admin/api/people?limit=` — social_db kişi listesi
- GET `/admin/api/profiles` — realtime profil + subagent özeti
- GET `/admin/api/config` — runtime registry anahtarları
- GET `/admin/api/hardware` — donanım varlık haritası (arduino/esp_link/camera/neopixel/imx500)
- GET `/admin/api/all` — yukarıdaki tüm anlık görüntüler tek payload'da
- POST `/admin/api/profile/switch` `{ name }` — realtime profilini atomik değiştirir (agent_core + vlm_bridge + ollama num_predict)
- GET `/admin/api/stream` — SSE durum akışı (`event: status`, periyodik + keep-alive)

Token gerektiren uç noktalarda, token `auth.header` ile belirtilen HTTP header'ında gönderilir (varsayılan `X-Admin-Token`).

## Config Anahtarları (`config/config.yml`)
- `enabled` — modülün etkin olup olmadığı
- `mount_prefix` — router prefix'i (varsayılan `/admin`)
- `bind_lan_only` — LAN dışı istemcileri reddet (varsayılan `true`)
- `allowed_networks` — izin verilen CIDR listesi
- `auth.token` — boşsa token zorunlu değildir; doluysa `auth.header` başlığıyla eşleşmelidir
- `auth.header` — token header adı (varsayılan `X-Admin-Token`)
- `sse.interval_s` — SSE snapshot aralığı (sn)
- `sse.heartbeat_s` — SSE keep-alive aralığı (sn)
