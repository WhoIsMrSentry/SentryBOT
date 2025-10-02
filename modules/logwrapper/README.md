# logwrapper (Merkezi Loglama Servisi)

Merkezi loglama için hafif bir modül. Tüm modüllerin loglarını tek yerde toplar.

Özellikler:
- Console + dönen dosya handler
- Bellek içi halka buffer (REST ile okunabilir)
- JSON veya okunabilir format
- Warnings -> logging
- Modül bazlı seviye override
- FastAPI router (opsiyonel)

## Kullanım

Kütüphane olarak:

```python
from modules.logwrapper import init_logging, get_router

init_logging()  # erken çağırın

# FastAPI ile entegrasyon (opsiyonel)
app = FastAPI()
router = get_router()
if router is not None:
    app.include_router(router)
```

CLI/servis gibi çalıştırma:

```bash
python -m modules.logwrapper.xLogService
```

## Konfigürasyon
`modules/logwrapper/config/config.yml` içinde. Ortam değişkenleri ve `init_logging(overrides=...)` ile override edilebilir.

- LOG_LEVEL: konsol seviyesi
- LOG_FILE: dosya yolu

## DryCode Notları

## Gateway Notu
Gateway içinde merkezi loglama başlatılması opsiyoneldir; mevcut kurulumda gateway başlarken `init_logging()` çağrısı denenir. Başarısız olsa bile modüller çalışmaya devam eder.
- Tek sorumluluk: modül sadece log altyapısını kurar ve minimal API sunar.
- Dış bağımlılıklar: yalnızca opsiyonel `PyYAML` ve `FastAPI` (API için). Başka bağımlılık yok.
