# Arduino Serial

Arduino/ESP donanımına giden komutların tek kontrat kaynağı ve taşıma katmanıdır. Tüm Pi tarafı komutları `contract.py` içindeki `build_*` fonksiyonları üzerinden üretilmelidir; elle `{"cmd": ...}` payload yazımı yasaktır.

## Sorumluluklar

- NDJSON komut kontratı (`contract.py`)
- ESP HTTP transport (varsayılan üretim yolu)
- Opsiyonel legacy serial fallback
- ACK bekleyen `/arduino/request` akışı
- Heartbeat, retry ve eşzamanlılık koruması
- FastAPI router ve sürücü sınıfı

## Mimari

- Giriş noktası: `xArduinoSerialService.py`
- Kontrat: `contract.py`
- Router: `api/router.py`
- Sürücü: `services/driver.py`
- Konfigürasyon: `config/config.yml` + `config/agent.yaml`

## Kontrat Ailesi

`contract.py` içinde öne çıkan builder'lar:
- `build_set_servo_cmd`, `build_set_pose_cmd`
- `build_stepper_cmd`, `build_stepper_cfg_cmd`
- `build_track_cmd`, `build_drive_cmd`
- `build_liveliness_cmd`, `build_laser_cmd`, `build_buzzer_cmd`
- `build_lcd_cmd`, `build_tune_cmd`, `build_policy_cmd`

Bu builder'lar komutu üretir; gönderim `request`/`send` katmanında yapılır.

## API (Gateway altında `/arduino/*`)

- `GET /arduino/healthz`
- `POST /arduino/send` — fire-and-forget
- `POST /arduino/request` — ACK bekleyen kritik komutlar
- `POST /arduino/telemetry/start`, `/telemetry/stop`
- `GET /arduino/rfid/last`, `/rfid/authorize`
- `POST /arduino/cute/{name}`, `/cute/emotion/{emotion}`
- `POST /arduino/sound/out/{mode}`, `/buzzer`, `/sound/play/{name}`

Kritik hareket komutlarında `/arduino/request` tercih edilmelidir (timeout 0.8–1.5s).

## Konfigürasyon

- `transport`: `esp_http` (varsayılan) veya `serial`
- `esp_base_url`, `esp_request_path`, `esp_send_path`
- `heartbeat_ms`
- `rfid.allowed_uids`, `rfid.authorize_window_s`

Env override: `ARDUINO_PORT`, `ARDUINO_BAUD`

## İlişkiler

- `autonomy`, `speech`, `agent_core`, `vlm_bridge`, `animate` gibi modüller bu katman üzerinden donanıma erişir
- Gateway bootstrap sırasında Arduino servisi mount edilir ve NeoPixel/Autonomy ile kablolanır

## Kullanım

```python
from modules.arduino_serial.contract import build_set_servo_cmd, SERVO_INDEX_PAN

payload = build_set_servo_cmd(SERVO_INDEX_PAN, 90)
# Gateway: POST /arduino/request
```
