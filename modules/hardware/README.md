# Hardware

Raspberry Pi (SBC) donanım tanı diagnostic modülüdür. Sistem metrikleri, I2C tarama ve GPIO bilgisi sunar; ayrıca programatik HAL sınıfları export eder.

## Sorumluluklar

- Sistem snapshot: CPU sıcaklığı, 1 dk load average, throttle göstergesi
- I2C bus tarama (smbus2 ile, yoksa boş liste)
- GPIO mod bilgisi
- HAL sınıfları: `MotorService`, `ServoService`, `LightsService`, `AudioService` (REST değil, kütüphane)

## Mimari

- Giriş noktası: `xHardwareService.py`
- Snapshot: `services/system.py`
- I2C: `services/i2c.py`
- GPIO: `services/gpio.py`
- HAL: `services/motor_service.py`, `servo_service.py`, `lights_service.py`, `audio_service.py`

Gateway `_IMPORT_MODULES` ile `include.hardware=true` olduğunda mount edilir.

## API (Gateway altında `/hardware/*`)

- `GET /hardware/healthz` — `{ ok, system: snapshot }`
- `GET /hardware/system` — CPU sıcaklığı, load, throttle
- `GET /hardware/i2c/scan` — `{ bus, addresses: ["0x3c", ...] }`
- `GET /hardware/gpio/info` — GPIO mod özeti

Not: RAM/disk metrikleri bu modülde yok; `interactions` kendi `metrics.py` okuyucusunu kullanır.

## HAL Kullanımı (programatik)

```python
from modules.hardware import ServoService, MotorService
# ServiceClient (autonomy) ile HTTP üzerinden arduino/animate/neopixel çağrıları
```

`ServoService.run_animation()` → animate servisi; `MotorService.drive()` → stepper komutları.

## Konfigürasyon

`config/config.yml`:
- `i2c.bus` (genelde `1`)
- `gpio.mode` (genelde `bcm`)

## İlişkiler

- `interactions`: benzer CPU metrikleri kendi içinde okunur (REST bağımlılığı yok)
- `autonomy`: HAL sınıfları agent/orchestrator proprioception için
- `oled_faces`, `neopixel`: I2C debug sırasında adres doğrulama

Otonom karar üretmez; montaj/debug ve agent HAL katmanıdır.
