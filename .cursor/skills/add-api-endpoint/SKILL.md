---
name: add-api-endpoint
description: SentryBOT: Add API Endpoint â€” Mevcut ModÃ¼le Endpoint Ekleme. Source: .sentrybot/skills/add-api-endpoint.md
---
# Skill: Add API Endpoint â€” Mevcut ModÃ¼le Endpoint Ekleme

> Mevcut bir modÃ¼le yeni API endpoint ekleme prosedÃ¼rÃ¼.

## Girdiler

| Parametre | Zorunlu | AÃ§Ä±klama | Ã–rnek |
|-----------|---------|----------|-------|
| `MODULE_NAME` | âœ… | Hedef modÃ¼l | `speak` |
| `ENDPOINT_PATH` | âœ… | Yeni endpoint yolu | `/volume` |
| `HTTP_METHOD` | âœ… | HTTP metodu | `POST` |
| `DESCRIPTION` | âœ… | Endpoint aÃ§Ä±klamasÄ± | `Ses seviyesini ayarla` |

## ProsedÃ¼r

### AdÄ±m 1: Mevcut Router'Ä± Ä°ncele
```bash
# Mevcut endpoint'leri gÃ¶r
cat modules/{{MODULE_NAME}}/api/router.py
```

Kontrol et:
- Naming convention (fonksiyon isimleri)
- Parametre alma kalÄ±bÄ± (query param vs body)
- Response formatÄ± (JSONResponse vs dict)
- Dependency injection (service instance nasÄ±l aktarÄ±lÄ±yor)

### AdÄ±m 2: Service Fonksiyonu OluÅŸtur (Gerekirse)

EÄŸer yeni iÅŸ mantÄ±ÄŸÄ± gerekiyorsa `services/` altÄ±na ekle:

```python
# modules/{{MODULE_NAME}}/services/<yeni_servis>.py
from __future__ import annotations
import logging

logger = logging.getLogger("{{MODULE_NAME}}.<yeni_servis>")


class <YeniServis>:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    def execute(self, **kwargs):
        """Ä°ÅŸ mantÄ±ÄŸÄ±."""
        logger.info("Executing with %s", kwargs)
        # ...implementasyon...
        return {"ok": True}
```

### AdÄ±m 3: Router'a Endpoint Ekle

```python
# modules/{{MODULE_NAME}}/api/router.py iÃ§ine ekle

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

### AdÄ±m 4: Config GÃ¼ncelle (Gerekirse)

EÄŸer yeni parametreler gerekiyorsa:

```yaml
# modules/{{MODULE_NAME}}/config/config.yml
# Mevcut ayarlarÄ±n altÄ±na ekle:
<yeni_alan>:
  enabled: true
  default_value: <deÄŸer>
```

### AdÄ±m 5: Test Ekle

```python
# modules/{{MODULE_NAME}}/tests/test_smoke.py iÃ§ine ekle

def test_{{endpoint_function_name}}_router():
    """{{ENDPOINT_PATH}} endpoint'i mevcut mu?"""
    from modules.{{MODULE_NAME}}.api.router import get_router
    router = get_router()
    paths = [r.path for r in router.routes]
    assert "{{ENDPOINT_PATH}}" in paths or any("{{ENDPOINT_PATH}}" in str(p) for p in paths)
```

### AdÄ±m 6: DokÃ¼mantasyon GÃ¼ncelle

1. `README.md` endpoint tablosuna yeni endpoint'i ekle
2. `architecture_{{MODULE_NAME}}.md` dosyasÄ±nÄ± gÃ¼ncelle
3. `.sentrybot/context/api-surface.md` dosyasÄ±nÄ± gÃ¼ncelle

## Kontrol Listesi

- [ ] Mevcut endpoint naming convention'a uyuyor
- [ ] Service fonksiyonu tek sorumluluk taÅŸÄ±yor
- [ ] Hata yakalama (try/except) var
- [ ] Config deÄŸeri hardcode deÄŸil
- [ ] Test yazÄ±ldÄ±
- [ ] DokÃ¼mantasyon gÃ¼ncellendi

