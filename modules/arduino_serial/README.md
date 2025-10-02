# Arduino Serial Module (NDJSON)

Arduino Mega ile NDJSON tabanlı seri haberleşme. Her satır bir JSON mesajı; firmware `xMain.ino` ile uyumlu.

## Özellikler
- PySerial tabanlı bağlantı, AUTO port keşfi (Windows/Mega 2560 öncelikli)
- Arkaplanda non-blocking okuma thread'i ve otomatik heartbeat
- Basit FastAPI router (opsiyonel) ve sürücü sınıfı
- DryCode: modüler yapı, ayrı config.yml
- Firmware komut kapsamı: hello/hb, set_servo, set_pose(duration), leg_ik, stepper(pos/vel), stepper_cfg,
    home/zero_now/zero_set, pid on/off, stand/sit, imu_read/imu_cal, eeprom_save/load, tune, policy, track,
  telemetry_start/stop, get_state, estop
    - Sit modunda stepper dengeleme + "drive" (kullanıcı hızı) karışımı desteklenir.

## Kurulum
- Python bağımlılıkları: `pyserial`, FastAPI kullanacaksanız `fastapi` ve `uvicorn`.

## Kullanım (kütüphane)
```python
from modules.arduino_serial.services.driver import ArduinoDriver

ardu = ArduinoDriver()
ardu.start()
print(ardu.hello())
ardu.set_head(90, 90)
# örnek: oturma + denge + ileri sürüş
ardu.svc.sit()
ardu.svc.drive(200)        # ileri gitme isteği (steps/s)
ardu.stop()
```

## API (opsiyonel)
Router oluşturmak için:
```python
from modules.arduino_serial.api.router import get_router
from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService

svc = xArduinoSerialService()
svc.start()
router = get_router(svc)
```

### Gateway Üzerinden Erişim
Gateway çalışırken Arduino uçları tek portta sunulur:
- GET  `/arduino/healthz`
- POST `/arduino/send`
- POST `/arduino/request`
- POST `/arduino/telemetry/start`
- POST `/arduino/telemetry/stop`

## Konfig
`modules/arduino_serial/config/config.yml` içinde varsayılanlar:
- port: AUTO (Arduino Mega otomatik bulunur)
- baudrate: 115200
- heartbeat_ms: 100

Env override: `ARDUINO_PORT`, `ARDUINO_BAUD`.

## Test
Basit smoke test `tests/test_smoke.py` fake transport ile çalışır.
