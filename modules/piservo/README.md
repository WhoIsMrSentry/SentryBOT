# PiServo (Ears) Module

İki servo ile “kulak” hareketleri: 90° yukarı, <90 öne eğik, >90 geriye eğik. Duygu ve olaylara göre poz verir.

## Servis Çalıştırma
```bash
uvicorn modules.piservo.xPiServoService:create_app --factory --host 0.0.0.0 --port 8093
```

## API
- GET  /piservo/healthz
- POST /piservo/set?left=90&right=90
- POST /piservo/emotion?name=joy
- POST /piservo/gesture?name=wakeword | sound
- POST /piservo/event?kind=wakeword | sound

## Duygu Eşlemesi
- EMOTION_POSES içinde: neutral, joy, fear, anger, sadness, surprise, curiosity

## Konfig
`modules/piservo/config/config.yml`
- left.gpio, right.gpio: servo sinyal pinleri
- PWM aralıkları, açı aralıkları `ServoConfig` ile koddan özelleştirilebilir.

Not: pigpio yoksa simülatör çalışır.