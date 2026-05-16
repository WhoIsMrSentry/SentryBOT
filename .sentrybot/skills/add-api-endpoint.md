# Skill: Add API Endpoint — Mevcut Modüle Endpoint Ekleme

> Mevcut bir modüle yeni API endpoint ekleme prosedürü.

## Girdiler

| Parametre | Zorunlu | Açıklama | Örnek |
|-----------|---------|----------|-------|
| `MODULE_NAME` | ✅ | Hedef modül | `speak` |
| `ENDPOINT_PATH` | ✅ | Yeni endpoint yolu | `/volume` |
| `HTTP_METHOD` | ✅ | HTTP metodu | `POST` |
| `DESCRIPTION` | ✅ | Endpoint açıklaması | `Ses seviyesini ayarla` |

## Prosedür

### Adım 1: Mevcut Router'ı İncele
```bash
# Mevcut endpoint'leri gör
cat modules/{{MODULE_NAME}}/api/router.py
```

Kontrol et:
- Naming convention (fonksiyon isimleri)
- Parametre alma kalıbı (query param vs body)
- Response formatı (JSONResponse vs dict)
- Dependency injection (service instance nasıl aktarılıyor)

### Adım 2: Service Fonksiyonu Oluştur (Gerekirse)

Eğer yeni iş mantığı gerekiyorsa `services/` altına ekle:

```python
# modules/{{MODULE_NAME}}/services/<yeni_servis>.py
from __future__ import annotations
import logging

logger = logging.getLogger("{{MODULE_NAME}}.<yeni_servis>")


class <YeniServis>:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    def execute(self, **kwargs):
        """İş mantığı."""
        logger.info("Executing with %s", kwargs)
        # ...implementasyon...
        return {"ok": True}
```

### Adım 3: Router'a Endpoint Ekle

```python
# modules/{{MODULE_NAME}}/api/router.py içine ekle

@router.{{HTTP_METHOD.lower()}}("{{ENDPOINT_PATH}}")
async def {{endpoint_function_name}}(request_body: dict = None):
    """{{DESCRIPTION}}"""
    try:
        result = svc.{{service_method}}(**request_body)
        return {"ok": True, "data": result}
    except Exception as e:
        logger.error("{{ENDPOINT_PATH}} failed: %s", e)
        return {"ok": False, "error": str(e)}
```

### Adım 4: Config Güncelle (Gerekirse)

Eğer yeni parametreler gerekiyorsa:

```yaml
# modules/{{MODULE_NAME}}/config/config.yml
# Mevcut ayarların altına ekle:
<yeni_alan>:
  enabled: true
  default_value: <değer>
```

### Adım 5: Test Ekle

```python
# modules/{{MODULE_NAME}}/tests/test_smoke.py içine ekle

def test_{{endpoint_function_name}}_router():
    """{{ENDPOINT_PATH}} endpoint'i mevcut mu?"""
    from modules.{{MODULE_NAME}}.api.router import get_router
    router = get_router()
    paths = [r.path for r in router.routes]
    assert "{{ENDPOINT_PATH}}" in paths or any("{{ENDPOINT_PATH}}" in str(p) for p in paths)
```

### Adım 6: Dokümantasyon Güncelle

1. `README.md` endpoint tablosuna yeni endpoint'i ekle
2. `architecture_{{MODULE_NAME}}.md` dosyasını güncelle
3. `.sentrybot/context/api-surface.md` dosyasını güncelle

## Kontrol Listesi

- [ ] Mevcut endpoint naming convention'a uyuyor
- [ ] Service fonksiyonu tek sorumluluk taşıyor
- [ ] Hata yakalama (try/except) var
- [ ] Config değeri hardcode değil
- [ ] Test yazıldı
- [ ] Dokümantasyon güncellendi
