# Logwrapper

SentryBOT'un merkezi log altyapısı modülüdür. Konsol, dönen dosya handler'ı ve bellek içi halka buffer üzerinden logları toplar.

## Sorumluluklar

- Global logging bootstrap (`init_logging`)
- Console + rotating file handler
- Bellek içi ring buffer (REST ile okunabilir)
- Modül bazlı seviye override
- Opsiyonel FastAPI router

## Mimari

- Giriş noktası: `xLogService.py`
- Handler'lar: `services/handlers.py`
- Rotasyon: `services/run_rotator.py`
- API: `api/router.py`

Graph'ta `init_logging` çağrıcıları:
- `sentrybot._configure_logging`
- `scripts.run_robot.main`
- Modül servisleri (opsiyonel erken init)

## API (Gateway altında `/logs/*`)

- `GET /logs/?n=200` — bellek ring-buffer içindeki son log kayıtları (`n` `1..5000` sınırlandırılır)
- `POST /logs/level` — logger seviyesi değiştirme (bilinmeyen seviyelerde HTTP `400`)

## Kullanım

```python
from modules.runtime_console.logwrapper import init_logging

init_logging()  # mümkün olduğunca erken
```

Gateway bootstrap sırasında log modülü mount edilebilir; başarısız olsa bile diğer modüller çalışmaya devam eder.
`separate_files.enabled: true` olduğunda `tui_file` yalnızca `runtime_console` logger'ına (`propagate: False`) bağlanır ve `root` handler'larına eklenmez; böylece `logs/tui.log` diğer modüllerle kirlenmez veya çift yazılmaz. `json_format: true` çıktıları `json.dumps` ile üretilir ve `InMemoryLogHandler` okumaları `self.lock` ile korunur.

## Konfigürasyon

`modules/runtime_console/logwrapper/config/config.yml`:
- konsol/dosya seviyeleri (`separate_files.enabled` kapalı olsa da `dictConfig` hatasız çalışır)
- format (JSON veya okunabilir)
- merkezi `DEFAULT_HIDDEN_PATHS` tabanlı `hidden_paths` gürültü filtresi
- modül bazlı override'lar

Env override: `LOG_LEVEL`, `LOG_FILE`

## İlişkiler

Logwrapper doğrudan otonom karar üretmez; ancak tüm modüllerin gözlemlenebilirliğini sağlar. Özellikle gateway + çok modüllü Pi5 runtime'ında merkezi teşhis katmanıdır.
