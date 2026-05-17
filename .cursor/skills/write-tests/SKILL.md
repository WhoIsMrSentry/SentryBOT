---
name: write-tests
description: SentryBOT: Write Tests â€” Test Yazma. Source: .sentrybot/skills/write-tests.md
---
# Skill: Write Tests â€” Test Yazma

> SentryBOT modÃ¼lleri iÃ§in test yazma kurallarÄ± ve kalÄ±plarÄ±.

## Test TÃ¼rleri

### 1. Smoke Test (Zorunlu)
Her modÃ¼lde `tests/test_smoke.py` olmalÄ±:
```python
"""{{MODULE_NAME}} smoke testleri â€” temel saÄŸlÄ±k kontrolÃ¼."""

def test_import():
    """ModÃ¼l import edilebilir mi?"""
    from modules.{{MODULE_NAME}} import {{SERVICE_NAME}}Service
    assert {{SERVICE_NAME}}Service is not None

def test_config_loader():
    """Config yÃ¼klenebilir mi?"""
    from modules.{{MODULE_NAME}}.config_loader import load_config
    cfg = load_config()
    assert isinstance(cfg, dict)

def test_service_init():
    """Service boÅŸ config ile oluÅŸturulabilir mi?"""
    from modules.{{MODULE_NAME}} import {{SERVICE_NAME}}Service
    svc = {{SERVICE_NAME}}Service(cfg={})
    assert svc is not None

def test_router_creation():
    """API router oluÅŸturulabilir mi?"""
    from modules.{{MODULE_NAME}}.api.router import get_router
    router = get_router()
    assert router is not None
```

### 2. Unit Test
Tek bir fonksiyonu/sÄ±nÄ±fÄ± izole test etme:
```python
"""{{MODULE_NAME}} unit testleri."""
import pytest
from unittest.mock import MagicMock, patch

def test_specific_function():
    from modules.{{MODULE_NAME}}.services.some_service import SomeClass
    obj = SomeClass(cfg={"key": "value"})
    result = obj.do_something(input_data)
    assert result == expected_output

def test_error_handling():
    from modules.{{MODULE_NAME}}.services.some_service import SomeClass
    obj = SomeClass(cfg={})
    with pytest.raises(ValueError):
        obj.do_something(invalid_input)
```

### 3. API Test (FastAPI TestClient)
```python
"""{{MODULE_NAME}} API testleri."""
from fastapi.testclient import TestClient
from fastapi import FastAPI

def test_status_endpoint():
    from modules.{{MODULE_NAME}}.api.router import get_router
    app = FastAPI()
    app.include_router(get_router(), prefix="/{{MODULE_NAME}}")
    client = TestClient(app)
    resp = client.get("/{{MODULE_NAME}}/status")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
```

### 4. Mock KalÄ±plarÄ±
```python
# DonanÄ±m baÄŸÄ±mlÄ±lÄ±ÄŸÄ±nÄ± mock'la
@patch("modules.{{MODULE_NAME}}.services.hw.RPi.GPIO", create=True)
def test_hardware_function(mock_gpio):
    mock_gpio.input.return_value = 1
    # ...test...

# HTTP Ã§aÄŸrÄ±sÄ±nÄ± mock'la
@patch("httpx.AsyncClient.post")
async def test_service_client(mock_post):
    mock_post.return_value = MagicMock(status_code=200, json=lambda: {"ok": True})
    # ...test...

# Arduino serial'Ä± mock'la
@patch("modules.arduino_serial.xArduinoSerialService.ArduinoSerialService")
def test_arduino_command(mock_serial):
    mock_serial.request_cmd.return_value = {"ok": True}
    # ...test...
```

## CI KurallarÄ±
- Python 3.10 hedef
- `webrtcvad`, `sounddevice`, `soundfile` CI'da uninstall edilir
- DonanÄ±m gerektiren testler `@pytest.mark.skipif` ile korunur
- Timeout: collection 420s, test suite 1800s
- `--maxfail=1` ile ilk hatada durur

## Ã‡alÄ±ÅŸtÄ±rma
```bash
# Tek modÃ¼l
python -m pytest modules/{{MODULE_NAME}}/tests/ -v

# TÃ¼m modÃ¼ller
python -m pytest modules/ -q --maxfail=1

# Sadece collection kontrolÃ¼
python -m pytest --collect-only modules/{{MODULE_NAME}}/tests/ -vv
```

