# Platform - State Manager

SentryBOT'un paylaşılan global durum deposudur. Modüller arası operasyonel durum, duygu listesi ve serbest anahtar/değer bilgilerini tek noktada tutar.

## Sorumluluklar

- Thread-safe durum okuma ve güncelleme (`_lock` + ayrılmış `_persist_lock`)
- `operational` (izinli durum doğrulamalı) ve `emotions` için kısa yol endpoint'leri
- `subscribe()` / `unsubscribe()` ile süreç içi bildirim (`pubsub`) ve `GET /state/stream` SSE akışı
- İsteğe bağlı kalıcılık: `memory`, `json` (atomik `os.replace`), `sqlite` (`WAL` + `close()`)

## Mimari

- Giriş noktası: `xStateService.py` (`lifespan` kapanışında `store.close()`)
- **Router**: `api/router.py`
- **Depo**: `services/store.py` → `StateStore` (`_apply_updates` ortak yazım hattı)
- **Config**: `config_loader.py` → `modules.common.config_loader.load_module_config`

## API (Gateway altında `/state/*`)

- `GET /state/healthz`
- `GET /state/get?key=` — tüm durum veya tek anahtar (`?key=<name>`)
- `GET /state/stream` — Server-Sent Events (SSE) ile anlık snapshot ve durum değişim akışı
- `POST /state/set` — serbest key/value
- `POST /state/set/operational` — doğrulamalı operasyonel mod (`idle|active|busy|listening|speaking|thinking|sleep|sleeping|degraded|failed|maintenance|estop|error`)
- `POST /state/set/emotions` — aktif duygular listesi

## Konfigürasyon

`modules/system_control/state_manager/config/config.yml`:
- `server.host`, `server.port`
- `defaults` — başlangıç state'i
- `persistence.type` — `memory|json|sqlite` (default: `sqlite`)
- `persistence.path` — dosya yolu (sqlite: `modules/system_control/state_manager/data/state.sqlite3`, json: `data/state.json`)
- `pubsub.enabled` — süreç içi bildirim (default: true)

## İlişkiler (Güncel Modül Yolları)

- `autonomy` → `operational` state (idle/active), `emotions` (mood snapshot)
- `agent_core` → `emotions` (persona tone), `operational` (runtime profile)
- `expression` → `emotions` (semantic state sync)
- `platform/scheduler` → `kind: state_set` job'ları
- `platform/diagnostics` → `operational: degraded|failed`
- `platform/telemetry` → state metrics

## Bilinen Sorunlar

1. **PubSub Basit** - `services/store.py` içinde `pubsub.keys` dict'i, asyncio queue yok. Yüksek frekanslı update'lerde listener'lar bloklayabilir. `asyncio.Queue` + backpressure gerekli.
2. **SQLite Persistence Race** - `cognitive_memory` (social.db) ve `state_manager` (state.sqlite3) **ayrı dosya** ama aynı process. Eğer config yanlışsa aynı dosyayı kullanırlar → lock contention. Config validation eklenmeli.
3. **Transaction Isolation Yok** - `StateStore.set()` tek key atomic ama multi-key transaction yok. `operational` + `emotions` atomik yazılmak istenirse destek yok.
4. **Schema Yok** - Serbest key/value, tip güvenliği yok. `pydantic` model ile validation eklenmeli.
5. **PubSub Cross-Process Yok** - Sadece in-process. Multi-process (gunicorn workers) için Redis pub/sub gerekli.