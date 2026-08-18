# Calibration

Donanım kurulum ve geliştirme aşamasında kullanılan hafif kalibrasyon yardımcı modülüdür. Runtime otonomi akışına dahil değildir.

## Sorumluluklar

- Kamera checkerboard parametre önerisi
- Servo sweep profil parametreleri
- Montaj sırasında referans değer üretimi

## Mimari

- Giriş noktası: `xCalibrationService.py`
- Servisler: `services/camera_calib.py`, `services/servo_calib.py`
- Router: `api/router.py`

Gateway `_IMPORT_MODULES` ile `include.calibration=true` olduğunda mount edilir.

## API (Gateway altında `/calib/*`)

- `GET /calib/healthz`
- `GET /calib/camera/checkerboard?cols=9&rows=6&square_mm=25.0`
  - Dönen: `{ cols, rows, square_mm }` (parametre echo; gerçek kalibrasyon hesabı yok)
- `GET /calib/servo/sweep`
  - Dönen: `{ min: 0, max: 180, step: 10 }`

## Kullanım

Geliştirme/montaj sırasında gateway üzerinden çağrılır. Sonuçlar manuel olarak `piservo`, `arduino_serial` veya kamera config dosyalarına işlenir.

## Konfigürasyon

`config/config.yml` — modül-içi minimal ayarlar.

## İlişkiler

- `camera`: distorsiyon kalibrasyonu hedef modül
- `piservo` / `arduino_serial`: servo pulse/açı limitleri
- Otonomlukta kullanılmaz; setup/maintenance aracıdır
