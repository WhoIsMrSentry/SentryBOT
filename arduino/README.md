# SentryBOT Arduino Firmware

Bu dizin, biped robot firmware'ini içerir. Ana sketch `arduino/firmware/xMain/xMain.ino` altındadır. Firmware NDJSON seri protokolüyle haberleşir, 8 servo + 2 stepper, IMU tabanlı dengeleme, IK ve çeşitli çevre birimlerini destekler.

## Özellikler
- 8 Servo: L/R kalça, diz, bilek + baş tilt/pan (easing ile yumuşak)
- 2 Stepper (skate): hız ve konum modları, Sit modunda dengeleme
- IMU: MPU6050 (I2C)
- IK: 2D bacak ters kinematik + mirror
- NDJSON seri API @115200
- Modlar: Stand (servo dengeleme), Sit/Skate (stepper dengeleme)
- Güvenlik: heartbeat timeout, estop, açı sınırları
- Kalıcılık: IMU offset EEPROM kaydet/yükle
- Tuning: PID, servo/stepper parametreleri canlı ayar

## Bağlantı ve Kurulum
1) Seri port: `xConfig.h` içinde `SERIAL_IO` → `Serial` (USB) veya `Serial1` (RPi UART)
2) Gerekli kart/kütüphaneler: Arduino Mega 2560, (opsiyonel) MFRC522, LiquidCrystal_I2C
3) Yükleme: `arduino/firmware/xMain/xMain.ino`’yu açın, 115200 8N1.

## Servo Kontrolü (I2C PCA9685)
- `SERVO_USE_PCA9685` = 1 iken tüm servolar I2C üzerinden PCA9685 ile sürülür (varsayılan: 1).
- `PCA9685_ADDR` (varsayılan 0x40), `SERVO_FREQ_HZ` (50Hz), `SERVO_MIN_US`/`SERVO_MAX_US` (500..2500us) `xConfig.h`’den ayarlanır.
- Kanal eşlemesi için mevcut `PIN_*` tanımları PCA9685 kanal numarası (0..15) olarak kullanılır:
  - L HIP=0, L KNEE=1, L ANKLE=2
  - R HIP=15, R KNEE=14, R ANKLE=13
  - HEAD PAN=3, HEAD TILT=12
- Doğrudan Arduino Servo pinlerine dönmek isterseniz `SERVO_USE_PCA9685=0` yapın ve `PIN_*` değerlerini servo pinleriyle değiştirin.

Not:
- PCA9685 (servo sürücü) I2C üzerinde algılanamazsa firmware donmaz; servo yazmaları fail-safe olarak no-op olur ve LCD'de uyarı gösterilir.

## Lazer Kontrolü
- Tek lazer aç: `{ "cmd":"laser", "id":1, "on":true }` (veya id=2)
- Çift lazer aç: `{ "cmd":"laser", "both":true, "on":true }`
- Kapat: `{ "cmd":"laser", "on":false }`
- Pin ve polarite: `LASER1_PIN`, `LASER2_PIN`, `LASER_ACTIVE_HIGH` (`xConfig.h`).

## Güncel Pinler (Son Değişiklik)
- Lazerler: `LASER1_PIN=12`, `LASER2_PIN=11`
- Step/Dir: `PIN_STEPPER1_STEP=10`, `PIN_STEPPER1_DIR=9`, `PIN_STEPPER2_STEP=8`, `PIN_STEPPER2_DIR=7`
- IR: `IR_PIN=2`
- Buzzer: `BUZZER_LOUD_PIN=3`, `BUZZER_QUIET_PIN=4`
- Ultrasonik: `ULTRA_TRIG_PIN=6`, `ULTRA_ECHO_PIN=5`

## Dual Buzzer (Sesli/Sessiz)
- İki buzzer desteği vardır: `BUZZER_LOUD_PIN` ve `BUZZER_QUIET_PIN`.
- Bu seçim yazılımsal “mute” değil; fiziksel olarak iki ayrı çıkış seçilir (loud/quiet).
- Varsayılan çıkış seçimi (JSON): `{ "cmd":"sound", "out":"loud|quiet" }`
- Tek seferlik beep (JSON): `{ "cmd":"buzzer", "out":"loud|quiet", "freq":2200, "ms":60 }`
- Hazır ses çal (JSON): `{ "cmd":"sound_play", "name":"walle|bb8", "out":"loud|quiet" }`

## IR Remote Kontrol (Menü + Parametre)
- IR alıcı pini: `IR_PIN` (varsayılan 26)
- Tuşlar firmware içinde şu string’lere çevrilir: `0..9`, `*`, `#`, `UP`, `DOWN`, `LEFT`, `RIGHT`, `OK`.
- `LCD_ENABLED=1` ise IR menü geçişleri ve parametreler LCD'de 2 satır halinde gösterilir (son mesaj ~3 sn tutulur; `UNKNOWN` spam'ı yazdırılmaz).

### Kullanım Mantığı (Token)
- Komut girişi `*` ile başlar ve sayılar bir "token" olarak toplanır.
- Token şu durumlarda otomatik işlenir:
  - `IR_TOKEN_TIMEOUT_MS` (varsayılan 900ms) boyunca yeni rakam gelmezse
  - veya `*` / `OK` / `#` basılırsa

Örnek akış:
- `*1` → Menü 1 (Servo)
- `*4` → Servo seçimi (4. servo; 1-based)
- `*90` → 90 dereceye götür

### Menü Referansı
- Menü 1 (Servo): token1=servo(1..8 veya 0..7), token2=deg(0..180)
- Menü 2 (Drive): token=speed (steps/s) → `driveCmd`
- Menü 3 (Laser): token 1=on (both), token 0=off
- Menü 4 (Mode): 1=stand, 2=sit, 3=pid on, 4=pid off
- Menü 5 (Sound): 1=loud, 2=quiet

## Komut Referansı (Özet)
- Ping: `{ "cmd":"hello" }`
- Heartbeat: `{ "cmd":"hb" }`
- Tek servo: `{ "cmd":"set_servo", "index":0, "deg":90 }`
- Poz: `{ "cmd":"set_pose", "pose":[..8..], "duration_ms":1000 }`
- IK: `{ "cmd":"leg_ik", "x":120, "side":"L" }`
- Stepper: `{ "cmd":"stepper", "id":0, "mode":"pos|vel", "value":1000, "drive":200 }`
- Stepper cfg: `{ "cmd":"stepper_cfg", "maxSpeed":2000, "accel":1000 }`
- Homing: `{ "cmd":"home" }` / Sıfırla: `{ "cmd":"zero_now" }` / `{ "cmd":"zero_set", "p1":0, "p2":0 }`
- Mod: `{ "cmd":"stand" }` / `{ "cmd":"sit" }`
- IMU: `{ "cmd":"imu_read" }` / `{ "cmd":"imu_cal" }`
- PID: `{ "cmd":"pid", "enable":true }`
- Durum: `{ "cmd":"get_state" }`
- Telemetri: `{ "cmd":"telemetry_start", "interval_ms":50 }` / `{ "cmd":"telemetry_stop" }`
- Tuning: `{ "cmd":"tune", "pid":{...}, "skate":{...}, "servoSpeed":60 }`
- EEPROM: `{ "cmd":"eeprom_save" }` / `{ "cmd":"eeprom_load" }`
- Estop: `{ "cmd":"estop" }`

## Çevre Birimleri
- RFID (MFRC522): `{ "cmd":"rfid_last" }` ve olay yayını
- LCD (I2C): `{ "cmd":"lcd", "msg":"HELLO" }`
- Ultrasonik: `{ "cmd":"ultra_read" }`, kaçınma `{ "cmd":"avoid", "enable":true }`

### Dual LCD (I2C)
- 2 adet I2C LCD desteklenir: `LCD_I2C_ADDR` (mevcut ekran) + `LCD2_I2C_ADDR` (yeni ekran).
- Firmware açılışta I2C üzerinden ekranları algılar; biri yoksa diğeriyle devam eder.
- İki ekran da bağlıysa aynı mesajlar iki ekrana da basılır.
- Tek bir 16x2 LCD bağlıysa ve yanlışlıkla 16x1 gibi konfigüre edilmişse, firmware bunu otomatik 16x2 moda alır (2x8 görünümü engeller).

#### Seri Komut ile Hedef Seçimi
- Varsayılan yönlendirme (sonraki LCD mesajları hangi ekrana gitsin):
  - `{ "cmd":"lcd_route", "mode":"both" }` (ikisine)
  - `{ "cmd":"lcd_route", "mode":"1" }` (LCD1)
  - `{ "cmd":"lcd_route", "mode":"2" }` (LCD2)

- Tek mesajı hedefleyerek yazdırma:
  - LCD1: `{ "cmd":"lcd", "id":1, "msg":"HELLO" }`
  - LCD2: `{ "cmd":"lcd", "id":2, "msg":"WORLD" }`
  - İkisi: `{ "cmd":"lcd", "id":0, "msg":"BOTH" }`

- 2 satır yazdırma:
  - `{ "cmd":"lcd", "id":1, "top":"MENU:1", "bottom":"SERVO?" }`

## Notlar
- VS Code’ta `Arduino.h` uyarısı IntelliSense kaynaklıdır; Arduino IDE derlemesini etkilemez.
- RPi üzerinden UART bağlarken seviye dönüştürücü ve ortak GND şart.
- Heartbeat’i (50–100ms) kesmeyin; aksi halde estop tetiklenir.

## Boot Ekranı (Tanılama)
- `BOOT_STATUS_ENABLED=1` ise açılışta LCD'de algılanan modüller (LCD, IMU, PCA9685) ve eksikler kısa bir "boot checklist" olarak gösterilir.

## Lisans
Üst dizindeki `LICENSE` dosyasına bakın.
