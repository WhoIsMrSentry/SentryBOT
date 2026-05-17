---
name: add-service-class
description: SentryBOT: Add Service Class â€” Yeni Service SÄ±nÄ±fÄ± Ekleme. Source: .sentrybot/skills/add-service-class.md
---
# Skill: Add Service Class â€” Yeni Service SÄ±nÄ±fÄ± Ekleme

> Mevcut bir modÃ¼le yeni iÅŸ mantÄ±ÄŸÄ± sÄ±nÄ±fÄ± ekleme prosedÃ¼rÃ¼.

## Girdiler

| Parametre | Zorunlu | AÃ§Ä±klama | Ã–rnek |
|-----------|---------|----------|-------|
| `MODULE_NAME` | âœ… | Hedef modÃ¼l | `vlm_bridge` |
| `CLASS_NAME` | âœ… | SÄ±nÄ±f adÄ± (PascalCase) | `DepthEstimator` |
| `RESPONSIBILITY` | âœ… | Tek cÃ¼mle sorumluluk | `Derinlik haritasÄ± tahmini` |

## ProsedÃ¼r

### AdÄ±m 1: Mevcut Servisleri Ä°ncele
```bash
ls modules/{{MODULE_NAME}}/services/
cat modules/{{MODULE_NAME}}/services/__init__.py
```

### AdÄ±m 2: Yeni Service DosyasÄ± OluÅŸtur

```python
# modules/{{MODULE_NAME}}/services/{{class_name_snake}}.py
from __future__ import annotations
import logging

logger = logging.getLogger("{{MODULE_NAME}}.{{class_name_snake}}")


class {{CLASS_NAME}}:
    """{{RESPONSIBILITY}}"""

    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or {}
        self._initialized = False
        logger.info("{{CLASS_NAME}} created")

    def initialize(self) -> None:
        """Gecikmeli baÅŸlatma (lazy init)."""
        if self._initialized:
            return
        # BaÅŸlatma mantÄ±ÄŸÄ±
        self._initialized = True
        logger.info("{{CLASS_NAME}} initialized")

    def shutdown(self) -> None:
        """KaynaklarÄ± temizle."""
        self._initialized = False
        logger.info("{{CLASS_NAME}} shut down")
```

### AdÄ±m 3: `__init__.py`'ye Re-export Ekle

```python
# modules/{{MODULE_NAME}}/services/__init__.py
from .{{class_name_snake}} import {{CLASS_NAME}}  # noqa: F401
```

### AdÄ±m 4: x<Name>Service.py'den BaÅŸlat

```python
# x<Name>Service.py iÃ§inde __init__'e ekle:
from .services.{{class_name_snake}} import {{CLASS_NAME}}

class ...Service:
    def __init__(self, cfg=None):
        ...
        self.{{class_name_snake}} = {{CLASS_NAME}}(self.cfg.get("{{class_name_snake}}", {}))
```

### AdÄ±m 5: Test Yaz

```python
# modules/{{MODULE_NAME}}/tests/test_{{class_name_snake}}.py
def test_{{class_name_snake}}_init():
    from modules.{{MODULE_NAME}}.services.{{class_name_snake}} import {{CLASS_NAME}}
    instance = {{CLASS_NAME}}(cfg={})
    assert instance is not None
    assert not instance._initialized

def test_{{class_name_snake}}_initialize():
    from modules.{{MODULE_NAME}}.services.{{class_name_snake}} import {{CLASS_NAME}}
    instance = {{CLASS_NAME}}(cfg={})
    instance.initialize()
    assert instance._initialized

def test_{{class_name_snake}}_shutdown():
    from modules.{{MODULE_NAME}}.services.{{class_name_snake}} import {{CLASS_NAME}}
    instance = {{CLASS_NAME}}(cfg={})
    instance.initialize()
    instance.shutdown()
    assert not instance._initialized
```

## Kontrol Listesi

- [ ] SÄ±nÄ±f tek sorumluluk taÅŸÄ±yor
- [ ] Config'den okuma yapÄ±yor (hardcode yok)
- [ ] Lazy init destekliyor (gerekirse)
- [ ] Shutdown/cleanup metodu var
- [ ] `__init__.py`'ye re-export eklendi
- [ ] Test yazÄ±ldÄ±
- [ ] Architecture doc gÃ¼ncellendi

