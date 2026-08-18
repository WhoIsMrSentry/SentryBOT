# Scheduler

SentryBOT'un periyodik görev yöneticisidir. HTTP ping, konuşma, diagnostics, state güncelleme ve bildirim işlerini arka planda zamanlar.

## Sorumluluklar

- Runtime'da job ekleme/güncelleme/silme
- Periyodik HTTP istekleri (keep-alive, poll)
- Yerleşik job türleri: `speak`, `interaction_event`, `diagnostics`, `state_set`, `notify`
- Son çalıştırma sonuçlarını saklama

## Mimari

- Giriş noktası: `xSchedulerService.py`
- Motor: `services/runner.py` (`Scheduler`)
- Router: `api/router.py`

Gateway `_mount_scheduler` ile mount edilir; `include.scheduler=true` gerekir. Autostart açıksa startup'ta `Scheduler.start()` çağrılır.

## Job Türleri

| kind | Davranış |
|---|---|
| `http` | `url` veya gateway `path` üzerinden HTTP isteği |
| `speak` | `POST /speak/say` |
| `interaction_event` | `POST /interactions/event` |
| `diagnostics` | `POST /diagnostics/run` |
| `state_set` | `POST /state/set` |
| `notify` | `POST /notify/test` |

## API (Gateway altında `/scheduler/*`)

- `GET /scheduler/healthz`
- `GET /scheduler/jobs`
- `POST /scheduler/jobs` — job ekle/güncelle
- `DELETE /scheduler/jobs/{job_id}`
- `GET /scheduler/results`
- `POST /scheduler/run_once/{job_id}`

## Job Şeması (örnek)

```yaml
- id: hourly_diag
  kind: diagnostics
  every_s: 3600
  enabled: true
```

HTTP job:
```yaml
- id: gateway_ping
  kind: http
  method: GET
  path: /healthz
  every_s: 30
```

## Konfigürasyon

`config/config.yml`:
- `gateway_base_url`
- `jobs` — başlangıç job listesi

## İlişkiler

- `diagnostics`, `speak`, `interactions`, `state_manager`, `notifier`: hedef servisler
- Otonomlukta proaktif bakım ve periyodik davranış zamanlayıcısıdır
