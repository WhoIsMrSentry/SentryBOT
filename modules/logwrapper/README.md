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

- `GET /logs/?n=200` — son log kayıtları
- `POST /logs/level` — logger seviyesi değiştirme

## Kullanım

```python
from modules.logwrapper import init_logging

init_logging()  # mümkün olduğunca erken
```

Gateway bootstrap sırasında log modülü mount edilebilir; başarısız olsa bile diğer modüller çalışmaya devam eder.

## Konfigürasyon

`modules/logwrapper/config/config.yml`:
- konsol/dosya seviyeleri
- format (JSON veya okunabilir)
- modül bazlı override'lar

Env override: `LOG_LEVEL`, `LOG_FILE`

## İlişkiler

Logwrapper doğrudan otonom karar üretmez; ancak tüm modüllerin gözlemlenebilirliğini sağlar. Özellikle gateway + çok modüllü Pi5 runtime'ında merkezi teşhis katmanıdır.
