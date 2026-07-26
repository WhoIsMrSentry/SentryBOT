# Calibration Module

SentryBOT'un donanım parçalarını kalibre etmeye ve test etmeye yarayan yardımcı araçları içerir. Servolar için açı/pulse taraması (sweep) yapma ve kamera için satranç tahtası (checkerboard) kalibrasyon parametrelerini üretme gibi işlemleri barındırır.

## API Uç Noktaları

Tüm uç noktalar varsayılan olarak `/calib` prefix'i ile Gateway altında sunulur.

- `GET /calib/healthz`
  Servis durumunu kontrol eder.

- `GET /calib/camera/checkerboard`
  Kamera distorsiyon kalibrasyonu için kullanılacak satranç tahtası ölçülerini ve köşe noktası koordinat matrislerini önerir.
  **Parametreler:**
  - `cols` (int): Sütun köşe sayısı (varsayılan: 9)
  - `rows` (int): Satır köşe sayısı (varsayılan: 6)
  - `square_mm` (float): Her bir karenin mm cinsinden boyutu (varsayılan: 25.0)

- `GET /calib/servo/sweep`
  Servoların min/max mikrosaniye (us) değerlerini ve güvenli çalışma aralıklarını ayarlamak için kullanılacak sinyal tarama (sweep) profilini döndürür.

## Kullanım

Geliştirme veya donanım montaj aşamasında doğrudan Gateway üzerinden API uçlarına çağrı yapılarak kullanılır. Kalibrasyon sonuçları genellikle donanım konfigurasyon dosyalarına (`arduino_serial` veya `piservo`) işlenir.
