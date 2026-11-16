# Platform - Scheduler

SentryBOT'un periyodik görev yöneticisidir. HTTP ping, konuşma, diagnostics, state güncelleme ve bildirim işlerini arka planda zamanlar.

## Sorumluluklar

- Runtime'da doğrulanmış iş ekleme/güncelleme/silme (CRUD API + Pydantic `SchedulerJobPayload`)
- Paylaşımlı `httpx.AsyncClient` üzerinden periyodik veya günlük `"HH:MM"` (`modules.common.time_utils.parse_hhmm`) iş tetikleme
- `modules.common.job_types` (`JobContext` + `JobRegistry`) aracılığıyla yerleşik iş türleri: `speak`, `interaction_event`, `diagnostics`, `state_set`, `notify` (`/notify/telegram`|`/notify/discord`), `http`
- İş sonuçları belleği (`remove_job` sonrası temizlenir) ve dinamik işler için atomik JSON kalıcılığı (`persistence_path`)

## Mimari

- Giriş noktası: `xSchedulerService.py` (`services` + `persistence_path` desteği)
- **Motor**: `services/runner.py` → `Scheduler` (`add_or_update_job`, `remove_job`, `_seconds_until_next_hhmm`)
- **Router**: `api/router.py`
- **Config**: `config_loader.py` → `modules.common.config_loader.load_module_config` + `apply_bind_host(..., "SCHEDULER_HOST")`

Gateway `_mount_scheduler` ile mount edilir; `include.scheduler=true` gerekir. Autostart açıksa startup'ta `Scheduler.start()`, kapanışta `Scheduler.stop()` (client `aclose()` dahil) çağrılır.

## Job Türleri

| kind | Davranış | Parametreler |
|------|----------|--------------|
| `http` | `url` veya gateway `path` üzerinden HTTP isteği | `method`, `path`, `url`, `body`, `headers` |
| `speak` | `POST /speak/say` | `text`, `engine`, `tone` |
| `interaction_event` | `POST /interactions/event` | `type`, `data` |
| `diagnostics` | `POST /diagnostics/run` | - |
| `state_set` | `POST /state/set` (`set_value`) | `key`, `value` |
| `notify` | `POST /notify/telegram` / `/notify/discord` | `text`, `channel` |

## API (Gateway altında `/scheduler/*`)

- `GET /scheduler/healthz`
- `GET /scheduler/jobs`
- `POST /scheduler/jobs` — job ekle/güncelle
- `DELETE /scheduler/jobs/{job_id}`
- `GET /scheduler/results` — son çalışma sonuçları
- `POST /scheduler/run_once/{job_id}` — manuel tetikle

## Job Şeması (Örnek)

```yaml
# Periyodik diagnostics
- id: hourly_diag
  kind: diagnostics
  every_s: 3600
  enabled: true

# HTTP ping (gateway healthz)
- id: gateway_ping
  kind: http
  method: GET
  path: /healthz
  every_s: 30

# TTS announcement
- id: morning_greeting
  kind: speak
  text: "Günaydın!"
  every_s: 86400
  cron: "0 7 * * *"  # opsiyonel cron desteklenirse
```

## Konfigürasyon

`modules/system_control/scheduler/config/config.yml`:
- `gateway_base_url` — hedef gateway URL'si (override edilebilir)
- `jobs` — başlangıç job listesi (array)

## İlişkiler (Güncel Modül Yolları)

- `platform/diagnostics` → `kind: diagnostics` hedefi
- `voice/speak` → `kind: speak` hedefi
- `expression/interactions` → `kind: interaction_event` hedefi
- `platform/state_manager` → `kind: state_set` hedefi
- `platform/notifier` → `kind: notify` hedefi
- `platform/telemetry` → job sonuçları metrik olarak

**Not:** Config'deki `gateway_base_url` bootstrap'ta `started["gateway_base_url"]` ile override edilir.

## Bilinen Sorunlar (Güncel 2026-08-21, Tam Tarama)

1. **Job Kind Hardcoded ✅ FIXED (2026-08-21)** - `common/job_types.py:JobRegistry` YENİ 6 handler (`HTTP, Speak, InteractionEvent, Diagnostics, StateSet, Notify`) + `runner.py:164 get_job_registry` eklendi. Yeni kind `register_job_handler(MyHandler)` ile eklenir, `if/elif` kaldırıldı. Graph: `Scheduler 15 hit`.
2. **Self-Heal Döngüsü** - `diagnostics` job failed modüle heal POST atıyorsa, modül restart → diagnostics tekrar tetiklenir. Job `running` state'inde heal bitene kadar beklemeli.
3. **Persistence Yok** - Job sonuçları sadece memory `list_results:77` kopya. Restart sonrası kayıp. `common/persistence.py:PersistenceManager` ile SQLite adopt edilebilir.
4. **Cron Desteği Yok** - Sadece `every_s` interval. `cron` expression desteği (APScheduler style) eklenmeli.
5. **Concurrency Control** - Aynı job ID ile paralel çalışma engellenmiyor. `max_instances` parametresi `JobDefinition:job_types.py` eklendi ama `runner.py:109 _job_loop` henüz kullanmıyor.