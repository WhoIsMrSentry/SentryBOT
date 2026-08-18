# Animate

YAML tabanlı servo animasyon yürütücüsüdür. `arduino_serial.set_pose()` üzerinden kafa/gövde pozlarını adım adım oynatır; otonom karar üretmez, scriptlenmiş hareket sağlar.

## Sorumluluklar

- `animations/*.yml` dosyalarını okuma ve çalıştırma
- Hız çarpanı (`speed`) ve döngü (`loop`) desteği
- Legacy 8 değerli pozları 4-servo kontratına normalize etme (pan/tilt)
- Gateway üzerinden HTTP tetikleme

## Mimari

- Giriş noktası: `xAnimateService.py` (`xAnimateService`)
- Router: `api/router.py`
- Paylaşımlı `xArduinoSerialService` instance'ı gateway'den alınır

Gateway `_include_animate` arduino modülü mount edilmeden animate'i atlar (duplicate serial önleme).

## Yerleşik Animasyonlar

- `blink`, `look_around`, `owner_scan`, `sit`, `stretch`, `temp_owner`, `vision_focus`

## API (Gateway altında `/animate/*`)

- `GET /animate/list` — mevcut animasyon isimleri
- `POST /animate/run?name=&speed=1.0&loop=false` — thread'de çalıştırır (timeout korumalı)
- `POST /animate/stop` — çalışan animasyonu durdurur

## YAML Şeması

```yaml
name: sit
loop: false
steps:
  - pose: [90, 110, 60, 90]   # 4-servo: [pan, tilt, s2, s3]
    duration_ms: 1200
  - pose: [90, 110, 60, 90]
    hold_ms: 500
```

Legacy 8 değerli pozlarda son iki değer head tilt/pan olarak yorumlanır.

## Konfigürasyon

`config/config.yml`:
- `animations_dir` (null → varsayılan `modules/animate/animations`)
- `default_speed`, `run_timeout_s`

## İlişkiler

- `arduino_serial`: tek komut kaynağı (`set_pose`)
- `autonomy`: `ServiceClient.run_animation()` ve `companion_goal_executor` plan adımları
- `hardware.ServoService`: programatik animasyon tetikleme

Otonomlukta companion hedeflerinin fiziksel jest katmanıdır.
