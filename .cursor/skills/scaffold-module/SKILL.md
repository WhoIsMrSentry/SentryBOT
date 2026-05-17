---
name: scaffold-module
description: SentryBOT: Scaffold Module â€” SÄ±fÄ±rdan ModÃ¼l Ä°skeleti OluÅŸturma. Source: .sentrybot/skills/scaffold-module.md
---
# Skill: Scaffold Module â€” SÄ±fÄ±rdan ModÃ¼l Ä°skeleti OluÅŸturma

> Bu skill, SentryBOT modÃ¼l yapÄ± kurallarÄ±na uygun bir iskelet oluÅŸturur.

## Girdiler

| Parametre | Zorunlu | AÃ§Ä±klama | Ã–rnek |
|-----------|---------|----------|-------|
| `MODULE_NAME` | âœ… | ModÃ¼l adÄ± (snake_case) | `ultrasonic_sensor` |
| `SERVICE_NAME` | âœ… | Servis sÄ±nÄ±f adÄ± (PascalCase) | `UltrasonicSensor` |
| `PORT` | âŒ | Standalone port (varsa) | `8104` |
| `DESCRIPTION` | âœ… | KÄ±sa modÃ¼l aÃ§Ä±klamasÄ± | `Ultrasonik mesafe sensÃ¶rÃ¼ okuma` |
| `LAYER` | âœ… | Mimari katman | `AlgÄ± / Beyin / AI / Eylem / Arka Plan` |

## OluÅŸturulacak Dosyalar

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
{{SERVICE_NAME}} Service â€” {{DESCRIPTION}}
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
        """Servisi baÅŸlat."""
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
    """{{MODULE_NAME}} config dosyasÄ±nÄ± yÃ¼kle."""
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
# AÃ§Ä±klama: {{DESCRIPTION}}

server:
  host: 0.0.0.0
  port: {{PORT or 0}}

# ModÃ¼le Ã¶zgÃ¼ ayarlar buraya eklenir
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
        """ModÃ¼l durum kontrolÃ¼."""
        return {"ok": True, "module": "{{MODULE_NAME}}"}

    @router.get("/healthz")
    async def healthz():
        """SaÄŸlÄ±k kontrolÃ¼."""
        return {"status": "healthy"}

    return router
```

### 7. `modules/{{MODULE_NAME}}/services/__init__.py`

```python
"""{{SERVICE_NAME}} iÅŸ mantÄ±ÄŸÄ± servisleri."""
```

### 8. `modules/{{MODULE_NAME}}/tests/test_smoke.py`

```python
"""{{MODULE_NAME}} smoke testleri."""
import pytest


def test_import():
    """ModÃ¼l import edilebilir mi?"""
    from modules.{{MODULE_NAME}} import {{SERVICE_NAME}}Service
    assert {{SERVICE_NAME}}Service is not None


def test_config_loader():
    """Config yÃ¼klenebilir mi?"""
    from modules.{{MODULE_NAME}}.config_loader import load_config
    cfg = load_config()
    assert isinstance(cfg, dict)


def test_service_instantiation():
    """Service oluÅŸturulabilir mi?"""
    from modules.{{MODULE_NAME}} import {{SERVICE_NAME}}Service
    svc = {{SERVICE_NAME}}Service(cfg={})
    assert svc is not None


def test_router():
    """Router oluÅŸturulabilir mi?"""
    from modules.{{MODULE_NAME}}.api.router import get_router
    router = get_router()
    assert router is not None
    paths = [r.path for r in router.routes]
    assert "/status" in paths or any("/status" in str(p) for p in paths)
```

### 9. `modules/{{MODULE_NAME}}/architecture_{{MODULE_NAME}}.md`

```markdown
# {{SERVICE_NAME}} â€” Mimari DokÃ¼mantasyon

## Genel BakÄ±ÅŸ

{{DESCRIPTION}}

## ModÃ¼l YapÄ±sÄ±

\```
modules/{{MODULE_NAME}}/
â”œâ”€â”€ __init__.py
â”œâ”€â”€ x{{SERVICE_NAME}}Service.py
â”œâ”€â”€ config_loader.py
â”œâ”€â”€ config/
â”‚   â””â”€â”€ config.yml
â”œâ”€â”€ api/
â”‚   â”œâ”€â”€ __init__.py
â”‚   â””â”€â”€ router.py
â”œâ”€â”€ services/
â”‚   â””â”€â”€ __init__.py
â”œâ”€â”€ tests/
â”‚   â””â”€â”€ test_smoke.py
â”œâ”€â”€ architecture_{{MODULE_NAME}}.md
â””â”€â”€ README.md
\```

## Veri AkÄ±ÅŸÄ±

\```mermaid
flowchart TD
    API[API Ä°steÄŸi] --> SVC[{{SERVICE_NAME}}Service]
    SVC --> CFG[Config Loader]
    SVC --> BL[Ä°ÅŸ MantÄ±ÄŸÄ±]
    BL --> RES[YanÄ±t]
\```

## ModÃ¼ller ArasÄ± EtkileÅŸim

| ModÃ¼l | Ä°liÅŸki |
|---|---|
| `gateway` | Bootstrap ile mount edilir |

## TasarÄ±m KararlarÄ±

- DryCode prensiplerine uygun yapÄ±landÄ±rÄ±lmÄ±ÅŸtÄ±r.
- Config deÄŸerleri hardcode edilmez, config.yml Ã¼zerinden okunur.
```

### 10. `modules/{{MODULE_NAME}}/README.md`

```markdown
# {{SERVICE_NAME}} Module

**{{DESCRIPTION}}**

## Katman
{{LAYER}}

## KullanÄ±m

### KÃ¼tÃ¼phane olarak
\```python
from modules.{{MODULE_NAME}} import {{SERVICE_NAME}}Service
svc = {{SERVICE_NAME}}Service()
svc.start()
\```

### Servis olarak
Gateway bootstrap ile otomatik baÅŸlatÄ±lÄ±r.

## API Endpoint'leri

| Endpoint | Metod | AÃ§Ä±klama |
|----------|-------|----------|
| `/{{MODULE_NAME}}/status` | GET | ModÃ¼l durumu |
| `/{{MODULE_NAME}}/healthz` | GET | SaÄŸlÄ±k kontrolÃ¼ |

## KonfigÃ¼rasyon

| Ayar | VarsayÄ±lan | AÃ§Ä±klama |
|------|-----------|----------|
| `settings.enabled` | `true` | ModÃ¼l etkin mi |

## Testler
\```bash
python -m pytest modules/{{MODULE_NAME}}/tests/ -v
\```
```

## Ä°ÅŸlem SonrasÄ±

1. âœ… TÃ¼m dosyalarÄ±n oluÅŸturulduÄŸunu doÄŸrula
2. âœ… `python -c "from modules.{{MODULE_NAME}} import {{SERVICE_NAME}}Service"` Ã§alÄ±ÅŸtÄ±r
3. âœ… `python -m pytest modules/{{MODULE_NAME}}/tests/ -v` Ã§alÄ±ÅŸtÄ±r
4. â¡ï¸ Gateway bootstrap'a kayÄ±t iÃ§in `gateway-bootstrap` skill'ine geÃ§

