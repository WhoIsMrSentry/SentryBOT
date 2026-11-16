# PiServo (Ears)

İki servo ile robot kulak hareketlerini yönetir. Duygu, olay ve jest sinyallerini fiziksel kulak pozlarına çevirir.

## Sorumluluklar

- Sol/sağ kulak açı kontrolü (`0–180°`, ~50 Hz yumuşak ramp interpolasyonu + `idle_detach_ms` otomatik PWM kapatma)
- Duygu → kulak pozu eşlemesi (`EMOTION_POSES` + `common.emotion_vocab`)
- Jestler: `wakeword`, `sound` (iptal edilebilir `threading.Timer` ile `center_deg`'e dönüş), `vigilance`, `relax`, `idle`
- Çoklu backend: Tek paylaşılan `pigpio` / `lgpio` (RPi 5) / `sim` veya isteğe bağlı Arduino (`ServoConfig` aralığı + `wait_ack=False`)

## Mimari

- Giriş noktası: `xPiServoService.py` (FastAPI `lifespan` ile kapanışta PWM + GPIO temizliği)
- Koordinatör: `services/runner.py` (`EarRunner`, `RLock` + ramp & idle detach zamanlayıcıları)
- Sürücü: `services/driver.py` (`Servo`, `ServoConfig`, `create_pi_gpio_backend`)
- Duygu tablosu: `services/ears.py`
- Refleks: `services/ear_reflex.py` (`EarReflexEngine`, `time.monotonic()` cooldown)

Gateway `_include_piservo` ile mount edilir. Varsayılan donanımda kulaklar Pi GPIO 12/13'e bağlıdır (`arduino_index` tanımlı değildir).

## API (Gateway altında `/piservo/*`)

- `GET /piservo/healthz` (`ok`, aktif `backend`, varsa `error`)
- `GET /piservo/status` (mevcut/hedef açılar, `pwm_active`, `smooth_enabled`, `idle_detach_ms`)
- `POST /piservo/set?left=90&right=90` (`math.isfinite` ve aralık doğrulamalı; geçersiz girdide HTTP 400)
- `POST /piservo/emotion?name=joy` (veya JSON gövdesi `{"name": "joy"}`)
- `POST /piservo/gesture?name=wakeword|sound|vigilance|relax|idle` (bilinmeyende HTTP 400)
- `POST /piservo/reflex?angle=-45&energy=1.0` (`angle`/`energy` doğrulamalı)
- `POST /piservo/event?kind=doa:-45|sound:30|<gesture>`

## Duygu Eşlemesi

`neutral`, `joy`, `fear`, `anger`, `sadness`, `surprise`, `curiosity` — ayrıca `emotion_vocab` alias'ları (happy, sleepy vb.) otomatik çözülür.

## Konfigürasyon

`config/config.yml`:
```yaml
left:
  gpio: 12
  center_deg: 90.0
right:
  gpio: 13
  center_deg: 90.0
motion:
  smooth_enabled: true
  ramp_hz: 50.0
  max_speed_deg_s: 360.0
  idle_detach_ms: 800
```

Robot kafa pan/tilt Arduino Mega PCA9685 kanal 6/9'a; kulaklar RPi 5 GPIO 12/13'e aittir.

## İlişkiler

- `interactions`: `_wire_interactions_piservo` — wakeword, vision, emotion olayları
- `expression`: `ExpressionArbiter` → `PiServoAdapter.set_ears`
- `wakeword`, `speech`: dolaylı jest tetikleme
- `common.emotion_vocab`: kanonik duygu çözümlemesi

Otonomlukta duygusal durumun fiziksel kulak ifadesi katmanıdır.
