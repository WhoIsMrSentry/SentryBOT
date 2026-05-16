# Skill: Write Tests — Test Yazma

> SentryBOT modülleri için test yazma kuralları ve kalıpları.

## Test Türleri

### 1. Smoke Test (Zorunlu)
Her modülde `tests/test_smoke.py` olmalı:
```python
"""{{MODULE_NAME}} smoke testleri — temel sağlık kontrolü."""

def test_import():
    """Modül import edilebilir mi?"""
    from modules.{{MODULE_NAME}} import {{SERVICE_NAME}}Service
    assert {{SERVICE_NAME}}Service is not None

def test_config_loader():
    """Config yüklenebilir mi?"""
    from modules.{{MODULE_NAME}}.config_loader import load_config
    cfg = load_config()
    assert isinstance(cfg, dict)

def test_service_init():
    """Service boş config ile oluşturulabilir mi?"""
    from modules.{{MODULE_NAME}} import {{SERVICE_NAME}}Service
    svc = {{SERVICE_NAME}}Service(cfg={})
    assert svc is not None

def test_router_creation():
    """API router oluşturulabilir mi?"""
    from modules.{{MODULE_NAME}}.api.router import get_router
    router = get_router()
    assert router is not None
```

### 2. Unit Test
Tek bir fonksiyonu/sınıfı izole test etme:
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

### 4. Mock Kalıpları
```python
# Donanım bağımlılığını mock'la
@patch("modules.{{MODULE_NAME}}.services.hw.RPi.GPIO", create=True)
def test_hardware_function(mock_gpio):
    mock_gpio.input.return_value = 1
    # ...test...

# HTTP çağrısını mock'la
@patch("httpx.AsyncClient.post")
async def test_service_client(mock_post):
    mock_post.return_value = MagicMock(status_code=200, json=lambda: {"ok": True})
    # ...test...

# Arduino serial'ı mock'la
@patch("modules.arduino_serial.xArduinoSerialService.ArduinoSerialService")
def test_arduino_command(mock_serial):
    mock_serial.request_cmd.return_value = {"ok": True}
    # ...test...
```

## CI Kuralları
- Python 3.10 hedef
- `webrtcvad`, `sounddevice`, `soundfile` CI'da uninstall edilir
- Donanım gerektiren testler `@pytest.mark.skipif` ile korunur
- Timeout: collection 420s, test suite 1800s
- `--maxfail=1` ile ilk hatada durur

## Çalıştırma
```bash
# Tek modül
python -m pytest modules/{{MODULE_NAME}}/tests/ -v

# Tüm modüller
python -m pytest modules/ -q --maxfail=1

# Sadece collection kontrolü
python -m pytest --collect-only modules/{{MODULE_NAME}}/tests/ -vv
```
