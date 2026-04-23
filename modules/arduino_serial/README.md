# Arduino Serial Module (NDJSON Contract + ESP Transport)

Arduino komut kontratını (`contract.py`) tek kaynak olarak tutar ve üretimde komutları ESP bridge üzerinden Mega'ya iletir.

## Özellikler
- ESP HTTP transport (üretim): Pi -> ESP -> Mega
- Opsiyonel legacy serial fallback (`transport: serial`)
- Otomatik heartbeat ve request retry
- Basit FastAPI router (opsiyonel) ve sürücü sınıfı
- DryCode: modüler yapı, ayrı config.yml
- Firmware komut kapsamı: hello/hb, set_servo, set_pose(duration), stepper(pos/vel), stepper_cfg,
  home/zero_now/zero_set, pid_enable/pid_set/pid_status, stand/sit, imu_read/imu_cal, eeprom_save/load, tune, policy, track,
  telemetry_start/stop, get_state, estop
    - Sit modunda stepper dengeleme + "drive" (kullanıcı hızı) karışımı desteklenir.

## Kurulum
- Python bağımlılıkları: `requests`, `pyserial` (legacy fallback), FastAPI kullanacaksanız `fastapi` ve `uvicorn`.

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

## Builder Mantigi (Basit Anlatim)
- `contract.py` icindeki `build_*` fonksiyonlari, Arduino komutunu tek tip formatta uretir.
- Amaç: Her modulde elle `{"cmd": ...}` yazip farkli format gonderme riskini azaltmak.
- Ornek:
    - Eski: Kod icinde dogrudan `{"cmd":"stepper","id":0,...}` yaziliyordu.
    - Yeni: `build_stepper_cmd(...)` kullaniliyor ve her yerde ayni JSON cikiyor.
- Sonuc: Hata ayiklama kolaylasir, alan isimleri (`index/deg`, `head_pan`, vb.) karismaz.
- Not: Builder, komutu sadece uretir; gonderme islemini yine servis (`send/request`) yapar.

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
- GET  `/arduino/rfid/last` → Son görülen kart UID'sini ve kaç saniye önce okunduğunu döner.
- GET  `/arduino/rfid/authorize` → `config.yml` içindeki `rfid.allowed_uids` listesine göre kartı doğrular; `authorized: true` ise Autonomy içindeki RFID koruması açılır.
- POST `/arduino/cute/{name}` → CuteBuzzer sesi çal (`connection`, `disconnection`, `button_pushed`, `mode1`, `mode2`, `mode3`, `surprise`, `ohooh`, `ohooh2`, `cuddly`, `sleeping`, `happy`, `super_happy`, `happy_short`, `sad`, `confused`, `fart1`, `fart2`, `fart3`, `jump`).
- GET  `/arduino/cute/catalog` → Ses→NeoPixel animasyon/renk eşleşme tablosunu ve emotion map'i döner (Swagger'da görünür).
- POST `/arduino/cute/emotion/{emotion}` → Emotion adına göre uygun Cute sesi çalar (`happy`, `super_happy`, `sad`, `surprise`, `confused`, `sleeping`, `connected`, `disconnected`).
- POST `/arduino/sound/out/{mode}` → Varsayılan buzzer çıkışını değiştir (`loud|quiet`).
- POST `/arduino/buzzer?freq=2200&ms=60&out=loud` → Tek beep komutu.
- POST `/arduino/sound/play/{name}?out=quiet` → Firmware şarkı isimlerini çal.

Not:
- Kritik hareket komutlarında `POST /arduino/request` tercih edilmelidir (ACK/error döner).
- `POST /arduino/send` fire-and-forget içindir.
- Gateway, desteklenen Arduino komut aileleri için payload doğrulaması yapar; şekli/alanı hatalı isteklerde `400` döner.

## Konfig
`modules/arduino_serial/config/config.yml` içinde varsayılanlar:
- transport: `esp_http`
- esp_base_url: `http://sentrybot.local`
- esp_request_path: `/request`
- esp_send_path: `/send`
- heartbeat_ms: 100
- rfid.allowed_uids: Yetki verilecek kart UID'leri (HEX, büyük/küçük fark etmez)
- rfid.authorize_window_s: Son kart okumasının geçerli sayılacağı zaman penceresi (s)

Env override: `ARDUINO_PORT`, `ARDUINO_BAUD`.

## Test
Basit smoke test `tests/test_smoke.py` fake transport ile çalışır.
