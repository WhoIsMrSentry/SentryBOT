# Skill: Scaffold Module — Sıfırdan Modül İskeleti Oluşturma

> Bu skill, SentryBOT modül yapı kurallarına uygun bir iskelet oluşturur.

## Girdiler

| Parametre | Zorunlu | Açıklama | Örnek |
|-----------|---------|----------|-------|
| `MODULE_NAME` | ✅ | Modül adı (snake_case) | `ultrasonic_sensor` |
| `SERVICE_NAME` | ✅ | Servis sınıf adı (PascalCase) | `UltrasonicSensor` |
| `PORT` | ❌ | Standalone port (varsa) | `8104` |
| `DESCRIPTION` | ✅ | Kısa modül açıklaması | `Ultrasonik mesafe sensörü okuma` |
| `LAYER` | ✅ | Mimari katman | `Algı / Beyin / AI / Eylem / Arka Plan` |

## Oluşturulacak Dosyalar

### 1. `modules/{{MODULE_NAME}}/__init__.py`

```python
"""{{DESCRIPTION}}"""
from .x{{SERVICE_NAME}}Service import {{SERVICE_NAME}}Service  # noqa: F401

__all__ = ["{{SERVICE_NAME}}Service"]
```

### 2. `modules/{{MODULE_NAME}}/x{{SERVICE_NAME}}Service.py`

```python
from __future__ import annotations
"""
{{SERVICE_NAME}} Service — {{DESCRIPTION}}
"""
import logging
from .config_loader import load_config

logger = logging.getLogger("{{MODULE_NAME}}.service")


class {{SERVICE_NAME}}Service:
    """{{DESCRIPTION}}"""

    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or load_config()
        logger.info("{{SERVICE_NAME}}Service initialized")

    def start(self):
        """Servisi başlat."""
        logger.info("{{SERVICE_NAME}}Service starting")

    def stop(self):
        """Servisi durdur."""
        logger.info("{{SERVICE_NAME}}Service stopping")


def _include_{{MODULE_NAME}}(app, cfg: dict) -> dict:
    """Gateway bootstrap entegrasyon fonksiyonu."""
    from .api.router import get_router
    svc = {{SERVICE_NAME}}Service(cfg.get("{{MODULE_NAME}}", {}))
    app.include_router(get_router(svc), prefix="/{{MODULE_NAME}}", tags=["{{MODULE_NAME}}"])
    return {"{{MODULE_NAME}}": svc}
```

### 3. `modules/{{MODULE_NAME}}/config_loader.py`

```python
from __future__ import annotations
import os
import yaml
import logging

logger = logging.getLogger("{{MODULE_NAME}}.config")

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "config", "config.yml")


def load_config(path: str | None = None) -> dict:
    """{{MODULE_NAME}} config dosyasını yükle."""
    cfg_path = path or os.environ.get("{{MODULE_NAME.upper()}}_CONFIG", _DEFAULT_PATH)
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("Config not found at %s, using defaults", cfg_path)
        cfg = {}
    return cfg
```

### 4. `modules/{{MODULE_NAME}}/config/config.yml`

```yaml
# {{SERVICE_NAME}} Module Configuration
# Açıklama: {{DESCRIPTION}}

server:
  host: 0.0.0.0
  port: {{PORT or 0}}

# Modüle özgü ayarlar buraya eklenir
settings:
  enabled: true
```

### 5. `modules/{{MODULE_NAME}}/api/__init__.py`

```python
"""{{SERVICE_NAME}} API endpoints."""
```

### 6. `modules/{{MODULE_NAME}}/api/router.py`

```python
from __future__ import annotations
import logging
from fastapi import APIRouter

logger = logging.getLogger("{{MODULE_NAME}}.api")


def get_router(svc=None) -> APIRouter:
    router = APIRouter()

    @router.get("/status")
    async def status():
        """Modül durum kontrolü."""
        return {"ok": True, "module": "{{MODULE_NAME}}"}

    @router.get("/healthz")
    async def healthz():
        """Sağlık kontrolü."""
        return {"status": "healthy"}

    return router
```

### 7. `modules/{{MODULE_NAME}}/services/__init__.py`

```python
"""{{SERVICE_NAME}} iş mantığı servisleri."""
```

### 8. `modules/{{MODULE_NAME}}/tests/test_smoke.py`

```python
"""{{MODULE_NAME}} smoke testleri."""
import pytest


def test_import():
    """Modül import edilebilir mi?"""
    from modules.{{MODULE_NAME}} import {{SERVICE_NAME}}Service
    assert {{SERVICE_NAME}}Service is not None


def test_config_loader():
    """Config yüklenebilir mi?"""
    from modules.{{MODULE_NAME}}.config_loader import load_config
    cfg = load_config()
    assert isinstance(cfg, dict)


def test_service_instantiation():
    """Service oluşturulabilir mi?"""
    from modules.{{MODULE_NAME}} import {{SERVICE_NAME}}Service
    svc = {{SERVICE_NAME}}Service(cfg={})
    assert svc is not None


def test_router():
    """Router oluşturulabilir mi?"""
    from modules.{{MODULE_NAME}}.api.router import get_router
    router = get_router()
    assert router is not None
    paths = [r.path for r in router.routes]
    assert "/status" in paths or any("/status" in str(p) for p in paths)
```

### 9. `modules/{{MODULE_NAME}}/architecture_{{MODULE_NAME}}.md`

```markdown
# {{SERVICE_NAME}} — Mimari Dokümantasyon

## Genel Bakış

{{DESCRIPTION}}

## Modül Yapısı

\```
modules/{{MODULE_NAME}}/
├── __init__.py
├── x{{SERVICE_NAME}}Service.py
├── config_loader.py
├── config/
│   └── config.yml
├── api/
│   ├── __init__.py
│   └── router.py
├── services/
│   └── __init__.py
├── tests/
│   └── test_smoke.py
├── architecture_{{MODULE_NAME}}.md
└── README.md
\```

## Veri Akışı

\```mermaid
flowchart TD
    API[API İsteği] --> SVC[{{SERVICE_NAME}}Service]
    SVC --> CFG[Config Loader]
    SVC --> BL[İş Mantığı]
    BL --> RES[Yanıt]
\```

## Modüller Arası Etkileşim

| Modül | İlişki |
|---|---|
| `gateway` | Bootstrap ile mount edilir |

## Tasarım Kararları

- DryCode prensiplerine uygun yapılandırılmıştır.
- Config değerleri hardcode edilmez, config.yml üzerinden okunur.
```

### 10. `modules/{{MODULE_NAME}}/README.md`

```markdown
# {{SERVICE_NAME}} Module

**{{DESCRIPTION}}**

## Katman
{{LAYER}}

## Kullanım

### Kütüphane olarak
\```python
from modules.{{MODULE_NAME}} import {{SERVICE_NAME}}Service
svc = {{SERVICE_NAME}}Service()
svc.start()
\```

### Servis olarak
Gateway bootstrap ile otomatik başlatılır.

## API Endpoint'leri

| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/{{MODULE_NAME}}/status` | GET | Modül durumu |
| `/{{MODULE_NAME}}/healthz` | GET | Sağlık kontrolü |

## Konfigürasyon

| Ayar | Varsayılan | Açıklama |
|------|-----------|----------|
| `settings.enabled` | `true` | Modül etkin mi |

## Testler
\```bash
python -m pytest modules/{{MODULE_NAME}}/tests/ -v
\```
```

## İşlem Sonrası

1. ✅ Tüm dosyaların oluşturulduğunu doğrula
2. ✅ `python -c "from modules.{{MODULE_NAME}} import {{SERVICE_NAME}}Service"` çalıştır
3. ✅ `python -m pytest modules/{{MODULE_NAME}}/tests/ -v` çalıştır
4. ➡️ Gateway bootstrap'a kayıt için `gateway-bootstrap` skill'ine geç
