# Skill: Add Service Class — Yeni Service Sınıfı Ekleme

> Mevcut bir modüle yeni iş mantığı sınıfı ekleme prosedürü.

## Girdiler

| Parametre | Zorunlu | Açıklama | Örnek |
|-----------|---------|----------|-------|
| `MODULE_NAME` | ✅ | Hedef modül | `vlm_bridge` |
| `CLASS_NAME` | ✅ | Sınıf adı (PascalCase) | `DepthEstimator` |
| `RESPONSIBILITY` | ✅ | Tek cümle sorumluluk | `Derinlik haritası tahmini` |

## Prosedür

### Adım 1: Mevcut Servisleri İncele
```bash
ls modules/{{MODULE_NAME}}/services/
cat modules/{{MODULE_NAME}}/services/__init__.py
```

### Adım 2: Yeni Service Dosyası Oluştur

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
        """Gecikmeli başlatma (lazy init)."""
        if self._initialized:
            return
        # Başlatma mantığı
        self._initialized = True
        logger.info("{{CLASS_NAME}} initialized")

    def shutdown(self) -> None:
        """Kaynakları temizle."""
        self._initialized = False
        logger.info("{{CLASS_NAME}} shut down")
```

### Adım 3: `__init__.py`'ye Re-export Ekle

```python
# modules/{{MODULE_NAME}}/services/__init__.py
from .{{class_name_snake}} import {{CLASS_NAME}}  # noqa: F401
```

### Adım 4: x<Name>Service.py'den Başlat

```python
# x<Name>Service.py içinde __init__'e ekle:
from .services.{{class_name_snake}} import {{CLASS_NAME}}

class ...Service:
    def __init__(self, cfg=None):
        ...
        self.{{class_name_snake}} = {{CLASS_NAME}}(self.cfg.get("{{class_name_snake}}", {}))
```

### Adım 5: Test Yaz

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

- [ ] Sınıf tek sorumluluk taşıyor
- [ ] Config'den okuma yapıyor (hardcode yok)
- [ ] Lazy init destekliyor (gerekirse)
- [ ] Shutdown/cleanup metodu var
- [ ] `__init__.py`'ye re-export eklendi
- [ ] Test yazıldı
- [ ] Architecture doc güncellendi
