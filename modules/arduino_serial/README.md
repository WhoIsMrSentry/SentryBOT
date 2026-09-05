# Arduino Serial

Arduino/ESP donanımına giden komutların tek kontrat kaynağı ve taşıma katmanıdır. Tüm Pi tarafı komutları `contract.py` içindeki `build_*` fonksiyonları üzerinden üretilmelidir; elle `{"cmd": ...}` payload yazımı **yasaktır**.

## Sorumluluklar

- NDJSON komut kontratı (`contract.py`) - **Tek kaynak**
- **Transport Abstraction** (YENİ): `transports/` - `SerialTransport`, `ESPHTTPTransport`
- ESP HTTP transport (varsayılan üretim yolu)
- Opsiyonel legacy serial fallback
- ACK bekleyen `/arduino/request` akışı
- Heartbeat, retry ve eşzamanlılık koruması
- FastAPI router ve servis sınıfı
- **Command Validators** (YENİ): `command_validators.py`, `contract_validators.py` - payload doğrulama

## Mimari (Güncel: 2026-08-20)

- Giriş noktası: `xArduinoSerialService.py`
- **Kontrat**: `contract.py` → `build_*_cmd` fonksiyonları (builder pattern)
- **Transport Layer**: `transports/` (ortak bir base dosya/sınıf yoktur; transport arayüzü doğrudan her transport dosyası içinde tanımlıdır):
  - `serial_transport.py` → `SerialTransport` (pyserial, NDJSON line reader)
  - `esp_transport.py` → `ESPHTTPTransport` (HTTP + `/send`, `/request` endpoints)
- **Services**:
  - `services/serial_loops.py` → `SerialLoops` (read loop, heartbeat, event dispatch)
  - `services/port_detector.py` → `PortDetector` (auto port detection)
  - `services/rfid_handler.py` → `RFIDHandler` (UID allowlist, authorize window)
  - `services/cute_catalog.py` → `CuteCatalog` (predefined animation sequences)
- **Validators**:
  - `command_validators.py` - Outgoing command schema validation
  - `contract_validators.py` - Contract builder output validation
- **Router**: `api/router.py`
- **Konfigürasyon**: `config_loader.py` → `config/config.yml` + `config/agent.yaml`

## Kontrat Ailesi (Builder'lar - `contract.py`)

| Builder | Açıklama | Transport |
|---------|----------|-----------|
| `build_set_servo_cmd` | Tek servo pozisyonu | All |
| `build_set_pose_cmd` | Çoklu servo pose + duration | All |
| `build_stepper_cmd` | Stepper pos/vel/cfg | All |
| `build_stepper_cfg_cmd` | Stepper config | All |
| `build_track_cmd` | Head pan/tilt track (+drive) | All |
| `build_drive_cmd` | Differential drive | All |
| `build_liveliness_cmd` | Heartbeat/led pattern | All |
| `build_laser_cmd` | Laser on/off (single/both) | All |
| `build_buzzer_cmd` | Buzzer tone/pattern | All |
| `build_lcd_cmd` | LCD 16x1 write (8+8 chunk) | All |
| `build_tune_cmd` | PID/servo tune | All |
| `build_policy_cmd` | Safety policy (estop, cliff, etc) | All |
| `build_cute_cmd` | Predefined animation | All |
| `build_rfid_cmd` | RFID authorize/scan | All |

Bu builder'lar komutu üretir; gönderim `request`/`send` katmanında `transport.send(builder.build())` ile yapılır.

## API (Gateway altında `/arduino/*`)

- `GET /arduino/healthz`
- `POST /arduino/send` — Fire-and-forget (telemetry, non-critical)
- `POST /arduino/request` — **ACK bekleyen kritik komutlar** (pose, track, estop, stepper)
- `POST /arduino/telemetry/start|stop` — Telemetry stream kontrol
- `GET /arduino/rfid/last`, `GET /arduino/rfid/authorize`
- `POST /arduino/cute/{name}` — Cute catalog animasyonu
- `POST /arduino/cute/emotion/{emotion}` — Emotion → cute sequence
- `POST /arduino/sound/out/{mode}` — Audio output routing
- `POST /arduino/buzzer` — Buzzer tone
- `POST /arduino/sound/play/{name}` — Sound file playback
- `POST /arduino/laser/one/{which}`, `POST /arduino/laser/both`, `POST /arduino/laser/off` — Laser kontrolü
- `GET /arduino/cute/catalog` — Cute animasyon kataloğu
- `GET /arduino/metrics` — Servis metrikleri (rx/tx/ack sayaçları)

**Kritik hareket komutlarında** (`set_pose`, `track`, `stepper`, `estop`) **`/arduino/request` tercih edilmelidir** (timeout 0.8–1.5s, retry 2x).

## Transport Seçimi

`config/config.yml` → `transport`:
```yaml
transport: esp_http  # veya serial
esp_base_url: "http://192.168.4.1"  # ESP AP mode default
esp_request_path: "/request"
esp_send_path: "/send"
heartbeat_ms: 250
```

Serial fallback:
```yaml
transport: serial
port: "/dev/ttyACM0"  # veya ARDUINO_PORT env
baudrate: 115200
```

Env override: `ARDUINO_PORT`, `ARDUINO_BAUD`, `ARDUINO_TRANSPORT`

## İlişkiler (Güncel Modül Yolları)

**Consumer'lar (bu katman üzerinden donanıma erişir):**
- `autonomy/services/brain_parts/animations.py` → `arduino.track()`, `set_pose()`
- `expression/animate` → `arduino.set_pose()` (animasyon sekansları)
- `vlm_bridge/services/processor.py` → `arduino.track()` (face follow)
- `voice/speech/services/pan_tilt.py` → `arduino.track()` (DoA pan/tilt)
- `agent_core/services/tools/hardware_tools.py` → Tool'lar aracılığıyla
- `visual_output/neopixel` → Arduino NeoPixel bridge (event handler)

**Gateway Bootstrap Kablolaması:**
- `_wire_arduino_neopixel()` → Arduino event `neopixel_request` → NeoRunner
- `_wire_arduino_autonomy()` → Arduino hardware events (cliff, bump, estop) → Autonomy brain
- `_wire_arduino_autonomy()` → Arduino telemetry → Autonomy battery/imu

## Kullanım

```python
from modules.arduino_serial.contract import build_set_servo_cmd, SERVO_INDEX_PAN
from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService

# Servis üzerinden (gateway mount edilmişse)
arduino = xArduinoSerialService()
payload = build_set_servo_cmd(SERVO_INDEX_PAN, 90)
await arduino.request(payload)  # ACK bekler

# Veya doğrudan transport (testlerde)
from modules.arduino_serial.transports.serial_transport import SerialTransport
transport = SerialTransport(port="/dev/ttyACM0")
transport.connect()
transport.send(payload)
```

## Bilinen Sorunlar (Güncel 2026-08-21, Tam Tarama)

1. **xArduinoSerialService 298 satır (745 değil)** - Gerçek `xArduinoSerialService.py:46 298 satır`, KB→satır düzeltildi. Hala `RfidHandlerMixin+SerialLoopsMixin+EspTransportMixin+FirmwareHelpersMixin` 4 mixin, `TransportManager` ayrıştırılabilir ama öncelik düşük.
2. **HeadControlArbiter Bypass ✅ KISMEN DÜZELTİLDİ** - `head_arbiter_integration.py:70 extract_pan_tilt` + `xArduinoSerialService.py:46 head_arbiter_wrapper` + `bootstrap_hardware:_include_arduino:18` inject eklendi (2026-08-20). `trace_path HeadControlArbiter callers_total=4` artık `arduino_serial` de dahil. Kalan: `build_track_cmd:141` `head_tilt/head_pan` vs `tilt/pan` duplicate key temizliği.
3. **Duplicate Validators** - `command_validators.py` + `contract_validators.py` + `contract.py` builder inline -> `contract_validators.py:266 validate_arduino_payload` tek yer zaten, `command_validators` re-export, birleştirme gerekmez.
4. **ESP Transport Error Handling** - `esp_transport` timeout `esp_timeout 1.2s` `esp_connect_timeout 0.4s` `pause_after 5` `pause_sec 120` dağınık, `common/http_client.py` retry ile birleştirilebilir.