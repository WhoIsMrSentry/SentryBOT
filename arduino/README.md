# SentryBOT Arduino Firmware

Bu dizin, SentryBOT Arduino firmware'ini içerir. Ana sketch `arduino/firmware/xMain/xMain.ino` altındadır. Firmware NDJSON satır-tabanlı protokolü korur, ancak üretim topolojisinde Pi ile doğrudan değil ESP bridge üzerinden haberleşir.

Üretim veri yolu:
- Pi -> ESP32: HTTP (`/send`, `/request`)
- ESP32 -> Mega: UART1 NDJSON
- Mega: mevcut tüm komutları (ekran, lazer, buzzer, stepper, servo) işlemeye devam eder

ESP bridge kodu: `arduino/firmware/esp_bridge/esp_bridge.ino`

Not: Mevcut firmware davranışı ve pin/kanal eşlemeleri kaynak kodundaki `xConfig.h` ile belirlenir. Eski README içeriklerinde bazı değerler farklı versiyonlardan kalma olabilir; bu dosya güncel `xConfig.h` tanımlarına göre düzenlenmiştir.

## Özellikler
- 4 Servo: baş (pan, tilt) + iki adet Pi-servo/aksesuar (varsayılan yapı: easing ile yumuşak hareket)
- 2 Stepper (skate): hız ve konum modları, Sit modunda dengeleme
- IMU: MPU6050 (I2C)
- NDJSON seri API @115200
- Modlar: Stand ve Sit/Skate
- Güvenlik: heartbeat timeout, estop, açı sınırları
- Kalıcılık: IMU offset EEPROM kaydet/yükle
- Tuning: PID, servo/stepper parametreleri canlı ayar

## RAM ve String Optimizasyonu
- Cute neopixel retry kuyruğu artık `String` payload yerine sabit `char` buffer kullanır.
- Legacy IR menü kopyalarında (sound/servo/sensors) geçici `String` birleştirmeleri azaltıldı.

Bu değişiklikler, AVR tarafta heap parçalanmasını azaltmak ve uzun çalışmada kararlılığı artırmak içindir.

## Bağlantı ve Kurulum
1) Seri port: `xConfig.h` içinde `SERIAL_IO_PORT` ile seçilir.
  - `0=Serial`, `1=Serial1`, `2=Serial2`, `3=Serial3`
  - Varsayılan: Mega kartlarda `1` (TX1/RX1, ESP bridge hattı), diğer kartlarda `1`
2) Gerekli kart/kütüphaneler: Arduino Mega 2560 (veya uyumlu), (opsiyonel) MFRC522, LiquidCrystal_I2C, Adafruit_MPU6050, AccelStepper
3) Yükleme: `arduino/firmware/xMain/xMain.ino`’yu açın, 115200 8N1.

## Servo Kontrolü (I2C PCA9685)
- `SERVO_USE_PCA9685` = 1 iken servolar I2C üzerinden PCA9685 ile sürülür (varsayılan: 1).
- `PCA9685_ADDR`, `SERVO_FREQ_HZ`, `SERVO_MIN_US`/`SERVO_MAX_US` `xConfig.h`’den ayarlanır.
- Mevcut `xConfig.h` konfigürasyonu için ana kanal eşlemesi:
  - `PIN_PAN` = 6 (head pan)
  - `PIN_TILT` = 9 (head tilt)
  - `PIN_PI_SERVO_1` = 7 (pi-servo 1)
  - `PIN_PI_SERVO_2` = 8 (pi-servo 2)

Not: Bu firmware sürümü `SERVO_COUNT_TOTAL = 4` ile derlenmiştir. Eğer 8-servo bacak kontrolü veya farklı bir kanal haritası istiyorsan `xConfig.h` ve ilgili kodlarda değişiklik gerekecektir.

## Güncel Pinler (xConfig.h ile uyumlu)
- Lazerler: `LASER1_PIN = 6`, `LASER2_PIN = 7` (polarite: `LASER_ACTIVE_HIGH`)
- Stepper STEP/DIR (şu anki `xConfig.h`):
  - `PIN_STEPPER1_STEP = 11`
  - `PIN_STEPPER1_DIR  = 12`
  - `PIN_STEPPER2_STEP = 9`
  - `PIN_STEPPER2_DIR  = 10`
- IR: `IR_PIN = 23`
- Buzzer: `BUZZER_LOUD_PIN = 2`, `BUZZER_QUIET_PIN = 3`
- Ultrasonik: `ULTRA_TRIG_PIN = 4`, `ULTRA_ECHO_PIN = 5`
- RFID (MFRC522): `RFID_SS_PIN = 53`, `RFID_RST_PIN = 49` (opsiyonel)

Bu değerler kodun kaynağındaki `xConfig.h` dosyasında tanımlıdır; fiziksel bağlantılarını bu değerlere göre doğrula.

## Lazer Kontrolü
- Tek lazer aç: `{ "cmd":"laser", "id":1, "on":true }` (veya id=2)
- Çift lazer aç: `{ "cmd":"laser", "both":true, "on":true }`
- Kapat: `{ "cmd":"laser", "on":false }`

## Ekran / Menü
Bu firmware tarafında 20x4 I2C LCD menü/durum ekranı desteklenir.

Yazılım notları:
- `xLcdHub` 20x4'ü hedef alacak şekilde çalışır. `LCD_COLS`/`LCD_ROWS` değerlerini `xConfig.h` içinde 20/4 olarak ayarlayabilirsin.
- OLED çizimi Arduino tarafında değil, Pi tarafındaki `modules/oled_faces` servisi tarafından sürülür.

## Dual Buzzer
- İki buzzer desteği: `BUZZER_LOUD_PIN` ve `BUZZER_QUIET_PIN`.
- Komut örnekleri:
  - `{ "cmd":"buzzer", "out":"loud", "freq":2200, "ms":60 }`
  - `{ "cmd":"sound_play", "name":"walle" }`

## IR Remote Kontrol (Menü + Parametre)
- IR alıcı pini: `IR_PIN` (varsayılan 2)
- Tuşlar firmware içinde şu string’lere çevrilir: `0..9`, `*`, `#`, `UP`, `DOWN`, `LEFT`, `RIGHT`, `OK`.

### Menü Kullanımı (kısa)
- HOME: `OK` menüyü açar; `UP/DOWN` ile gezinir, `OK` girer, `#` geri.
- Ana menü öğeleri: `SERVO`, `LASER`, `ULTRA`, `IMU`, `RFID`, `SOUND`, `REMOTE`, `CALIB`, `SYSTEM`.

## Komut Referansı (Özet)
- Ping: `{ "cmd":"hello" }`
- Heartbeat: `{ "cmd":"hb" }`
- Tek servo: `{ "cmd":"set_servo", "index":0, "deg":90 }`
- Poz (4 servo): `{ "cmd":"set_pose", "pose":[90,90,90,90], "duration_ms":1000 }`
- Stepper: `{ "cmd":"stepper", "id":0, "mode":"pos|vel", "value":1000, "drive":200 }`
- Stepper PID: `{ "cmd":"pid_enable", "id":0, "enable":true }`, `{ "cmd":"pid_set", "id":0, "kp":1.0, "ki":0.0, "kd":0.05, "target":100 }`
- Homing: `{ "cmd":"home" }`, sıfırlama: `{ "cmd":"zero_now" }`, `{ "cmd":"zero_set", "p1":0, "p2":0 }`
- IMU: `{ "cmd":"imu_read" }`, `{ "cmd":"imu_cal" }`
- EEPROM: `{ "cmd":"eeprom_save" }`, `{ "cmd":"eeprom_load" }`
- Telemetri: `{ "cmd":"telemetry_start", "interval_ms":50 }` / `{ "cmd":"telemetry_stop" }`

## Çevre Birimleri
- RFID (MFRC522): `{ "cmd":"rfid_last" }` ve olay yayını
- LCD (I2C 20x4): `{ "cmd":"lcd", "top":"LINE1", "bottom":"LINE2" }`
- Ultrasonik: `{ "cmd":"ultra_read" }`, kaçınma `{ "cmd":"avoid", "enable":true }`

## Lisans
Üst dizindeki `LICENSE` dosyasına bakın.
