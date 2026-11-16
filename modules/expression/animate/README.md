# Animate

YAML tabanlı servo animasyon yürütücüsüdür. `arduino_serial.set_pose()` üzerinden kafa/gövde pozlarını adım adım oynatır; otonom karar üretmez, scriptlenmiş hareket sağlar.

## Sorumluluklar

- `animations/*.yml` dosyalarını okuma ve çalıştırma
- Hız çarpanı (`speed`) ve döngü (`loop`) desteği
- Multimodal eşzamanlı kanal desteği: Arduino servoları, PiServo kulakları, OLED yüz/göz ifadeleri ve NeoPixel ışık efektleri
- Gateway üzerinden HTTP tetikleme

## Mimari

- Giriş noktası: `xAnimateService.py` (`xAnimateService`)
- Router: `api/router.py`
- Paylaşımlı `xArduinoSerialService`, `piservo`, `oled_faces` ve `neopixel` instance'ları Gateway bootstrap (`_wire_animate_piservo`) üzerinden otomatik bağlanır

## Yerleşik Animasyonlar

- `blink`, `look_around`, `owner_scan`, `sit`, `stretch`, `temp_owner`, `vision_focus`

## API (Gateway altında `/animate/*`)

- `GET /animate/list` — mevcut animasyon isimleri
- `GET /animate/status` — aktif animasyon adı, adım indeksi (`step_index`), toplam adım, `loop` ve `degraded` durumu
- `POST /animate/run?name=&speed=1.0&loop=false` — ön-doğrulama sonrası `_run_lock` + kesilebilir `Event.wait` ile çalıştırır (`speed <= 0` veya traversal → 400, eksik dosya → 404)
- `POST /animate/stop?return_to_rest=false` — çalışan animasyonu anında keser ve opsiyonel olarak `rest_pose` konumuna döndürür

## Multimodal YAML Şeması

```yaml
name: sit
loop: false
steps:
  - pose: [90, 90, 70, 110]   # pan, tilt, ear_l, ear_r
    face: happy_eyes          # OLED yüz/göz ifadesi
    led: [0, 255, 128]        # NeoPixel RGB rengi
    duration_ms: 1200
    hold_ms: 500
```

Legacy 8 değerli pozlarda son iki değer head tilt/pan olarak yorumlanır.

## Konfigürasyon

`modules/expression/animate/config/config.yml`:
- `animations_dir` (`null` → varsayılan `modules/expression/animate/animations`)
- `default_speed` (varsayılan `1.0`)
- `interpolate` (`true` iken `duration_ms` servo easing ve adım zamanlamasında kullanılır)
- `run_timeout_s` (varsayılan `30.0`)
- `rest_pose`, `idle_breathing_period_s`, `idle_tilt_amp_deg`, `idle_ear_amp_deg` (`ProceduralMotionEngine` boşta nefes/kulak mikro salınımı için)

## İlişkiler

- `arduino_serial`: tek komut kaynağı (`set_pose`)
- `autonomy`: `ServiceClient.run_animation()` ve `companion_goal_executor` plan adımları
- `hardware.ServoService`: programatik animasyon tetikleme

Otonomlukta companion hedeflerinin fiziksel jest katmanıdır.
