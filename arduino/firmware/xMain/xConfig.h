#ifndef ROBOT_CONFIG_H
#define ROBOT_CONFIG_H
#include <Arduino.h>

// Board serial
#define ROBOT_SERIAL_BAUD 115200
// Select serial port for NDJSON link.
// SERIAL_IO_PORT options:
//   0 = Serial
//   1 = Serial1 (if available)
//   2 = Serial2 (if available)
//   3 = Serial3 (if available)
#ifndef SERIAL_IO_PORT
#if defined(ARDUINO_AVR_MEGA2560) || defined(ARDUINO_AVR_MEGA) || defined(__AVR_ATmega2560__)
#define SERIAL_IO_PORT 0
#else
#define SERIAL_IO_PORT 1
#endif
#endif

// You can still override everything by defining SERIAL_IO before including this header.
#ifndef SERIAL_IO
#if SERIAL_IO_PORT == 0
#define SERIAL_IO Serial
#elif SERIAL_IO_PORT == 1 && (defined(HAVE_HWSERIAL1) || defined(UBRR1H) || defined(USART1_RX_vect))
#define SERIAL_IO Serial1
#elif SERIAL_IO_PORT == 2 && (defined(HAVE_HWSERIAL2) || defined(UBRR2H) || defined(USART2_RX_vect))
#define SERIAL_IO Serial2
#elif SERIAL_IO_PORT == 3 && (defined(HAVE_HWSERIAL3) || defined(UBRR3H) || defined(USART3_RX_vect))
#define SERIAL_IO Serial3
#else
#define SERIAL_IO Serial
#endif
#endif

// Servo counts (pan/tilt + 2x Pi servo)
#define SERVO_COUNT_TOTAL 4

// Pins – adapt to your wiring
// NOTE: These are PCA9685 channel numbers (0..15) when `SERVO_USE_PCA9685==1`.
// If using direct Arduino pins (SERVO_USE_PCA9685==0), replace with digital pin numbers.
// PCA9685 channel mapping:
//  - 0..15: channels on the board. In this build we use four channels:
//    6 = pan, 9 = tilt, 7 = pi-servo-1 (ear), 8 = pi-servo-2 (ear)
// Pan/Tilt (PCA channel numbers)
#define PIN_PAN   6
#define PIN_TILT  9
// Pi servos (ears) — PCA channels
#define PIN_PI_SERVO_1 7
#define PIN_PI_SERVO_2 8

// Stepper pins (moved to avoid servo overlap)
// New Mega2560 wiring (user-provided)
// Motor1: DIR=12 STEP=11, Motor2: DIR=10 STEP=9
#define PIN_STEPPER1_DIR  12
#define PIN_STEPPER1_STEP 11
#define PIN_STEPPER2_DIR  10
#define PIN_STEPPER2_STEP 9
// Shared enable pin for both NEMA drivers
#ifndef PIN_STEPPER_ENABLE
#define PIN_STEPPER_ENABLE 8
#endif
// Active low by default (A4988/DRV8825 common)
#ifndef STEPPER_ENABLE_ACTIVE_LOW
#define STEPPER_ENABLE_ACTIVE_LOW 1
#endif
// Limit switch pins (optional). Use -1 to disable; active LOW by default.
#ifndef PIN_LIMIT1
#define PIN_LIMIT1 -1
#endif
#ifndef PIN_LIMIT2
#define PIN_LIMIT2 -1
#endif
#ifndef LIMIT_ACTIVE_LOW
#define LIMIT_ACTIVE_LOW 1
#endif

// Pan/Tilt limits
#define PAN_MIN  30
#define PAN_MAX  150
#define TILT_MIN 60
#define TILT_MAX 120

// Motion
#define SPEED_DEG_PER_S 60 // default easing speed

// IMU
#define IMU_I2C_ADDR 0x68

// Link safety & telemetry
#define HEARTBEAT_TIMEOUT_MS 500   // hb gelmezse bu sürede estop
#define TELEMETRY_MIN_INTERVAL_MS 20 // 50 Hz üstü riskli, altını öner

// PID (balance)
#define PID_PITCH_KP  0.8f
#define PID_PITCH_KI  0.02f
#define PID_PITCH_KD  0.05f
#define PID_ROLL_KP   0.8f
#define PID_ROLL_KI   0.02f
#define PID_ROLL_KD   0.05f
#define PID_OUT_LIMIT 15.0f  // deg of corrective hip offset cap
#define PID_SAMPLE_MS 10
#define PID_DEADBAND_DEG 2.0f
#define PID_MAX_ANGLE_DEG 45.0f

// Optional: enable serial-boot calibration prompt
#define BOOT_CALIBRATION_PROMPT 1

// Default poses
// Default poses: index mapping: 0=pan, 1=tilt, 2=pi_servo_1, 3=pi_servo_2
static const uint8_t POSE_STAND[SERVO_COUNT_TOTAL] = {90,90, 90,90};
static const uint8_t POSE_SIT[SERVO_COUNT_TOTAL]   = {90,90, 90,90};

// Stepper skate balance PID (inverted pendulum)
#define SKATE_KP  18.0f   // speed per degree
#define SKATE_KI  0.0f
#define SKATE_KD  0.8f    // speed per (deg/s)
#define SKATE_SPEED_LIMIT 2000.0f // steps/s cap

// =====================
// Closed-loop stepper PID (Hall feedback)
// Production-safe defaults: conservative gains, reasonable sampling period.
#ifndef STEPPER_PID_KP
#define STEPPER_PID_KP  1.0f
#endif
#ifndef STEPPER_PID_KI
#define STEPPER_PID_KI  0.0f
#endif
#ifndef STEPPER_PID_KD
#define STEPPER_PID_KD  0.05f
#endif
#ifndef STEPPER_PID_INTERVAL_MS
#define STEPPER_PID_INTERVAL_MS 50  // PID update period (ms)
#endif
#ifndef STEPPER_PID_MAX_OUTPUT
// Maximum commanded speed (absolute) the PID can emit (steps/s)
// Default to skate speed limit for safety
#define STEPPER_PID_MAX_OUTPUT SKATE_SPEED_LIMIT
#endif
#ifndef STEPPER_PID_INTEGRAL_LIMIT
// Clamp for integral term to avoid windup (in speed units*sec)
#define STEPPER_PID_INTEGRAL_LIMIT 10000.0f
#endif

// Steps mapping for rotation/translation commands used by IR controller
// Compute steps per revolution from motor full steps and gearbox ratio
// Motor full steps (e.g. NEMA17 = 200)
#ifndef STEPPER_MOTOR_FULLSTEPS
#define STEPPER_MOTOR_FULLSTEPS 200
#endif
// Gearbox reduction ratio expressed as (1 + NUM/DEN)
#ifndef GEARBOX_RATIO_NUM
#define GEARBOX_RATIO_NUM 38
#endif
#ifndef GEARBOX_RATIO_DEN
#define GEARBOX_RATIO_DEN 14
#endif
// Steps per output-shaft revolution (float) = MOTOR_FULLSTEPS * (1 + NUM/DEN)
#ifndef STEPPER_STEPS_PER_REV
#endif

// Microstepping (A4988 MS1/MS2/MS3). If MS pins are set to 5V for 1/16, set MICROSTEP=16.
#ifndef MICROSTEP
#define MICROSTEP 1
#endif

// Steps per output-shaft revolution (float) = MOTOR_FULLSTEPS * MICROSTEP * (1 + NUM/DEN)
#ifndef STEPPER_STEPS_PER_REV
#define STEPPER_STEPS_PER_REV ( (float)STEPPER_MOTOR_FULLSTEPS * (float)MICROSTEP * (1.0f + ((float)GEARBOX_RATIO_NUM / (float)GEARBOX_RATIO_DEN) ) )
#endif


// Steering defaults
#ifndef STEERING_FORWARD_DEG
#define STEERING_FORWARD_DEG 20.0f
#endif
// Inner wheel scale for turns (0.0 .. 1.0) — lower means sharper turn. 0.6 => inner wheel moves 60% of outer.
#ifndef STEERING_INNER_SCALE
#define STEERING_INNER_SCALE 0.6f
#endif

// EEPROM (kalibrasyon) - basit layout
#define EEPROM_MAGIC 0x42
#define EEPROM_ADDR_MAGIC   0
#define EEPROM_ADDR_IMU_OFF 1   // float2: offPitch, offRoll (8 byte)
// EEPROM addresses for persisted buzzer frequencies (uint16_t each)
#define EEPROM_ADDR_BUZZER_FREQ_LOUD 9
#define EEPROM_ADDR_BUZZER_FREQ_QUIET 11
// Validation byte for buzzer freq presence
#define EEPROM_ADDR_BUZZER_FREQ_MAGIC 13
#define EEPROM_BUZZER_MAGIC 0xA5

// EEPROM addresses for Hall encoder calibration
#define EEPROM_ADDR_HALL_MAGIC 100
#define EEPROM_ADDR_HALL_PPR_0 101 // uint16_t
#define EEPROM_ADDR_HALL_PPR_1 103 // uint16_t
#define EEPROM_HALL_MAGIC 0x5A

// EEPROM addresses for stepper PID persistence
#define EEPROM_ADDR_PID_MAGIC 200
#define EEPROM_ADDR_PID_KP_0 201 // float (4 bytes)
#define EEPROM_ADDR_PID_KI_0 205
#define EEPROM_ADDR_PID_KD_0 209
#define EEPROM_ADDR_PID_KP_1 213
#define EEPROM_ADDR_PID_KI_1 217
#define EEPROM_ADDR_PID_KD_1 221
#define EEPROM_PID_MAGIC 0xA6

// Stall detection (production-safe defaults)
#ifndef STEPPER_STALL_TIMEOUT_MS
#define STEPPER_STALL_TIMEOUT_MS 1000 // ms without pulses while target non-zero => stall
#endif
#ifndef STEPPER_STALL_MIN_PULSES_PER_INTERVAL
#define STEPPER_STALL_MIN_PULSES_PER_INTERVAL 1 // minimal pulses within interval to count as movement
#endif

// =====================
// Peripherals (optional)
// =====================

// Radio (nRF24 / EBYTE E01) default CE/CSN pins (override if needed)
#ifndef EBYTE_ENABLED
#define EBYTE_ENABLED 0
#endif
#ifndef RADIO_CE_PIN
#define RADIO_CE_PIN 47
#endif
#ifndef RADIO_CSN_PIN
#define RADIO_CSN_PIN 48
#endif
// Use hardware SPI pins for NRF24 (Mega hardware SPI: MOSI=51, MISO=50, SCK=52)
// Optional IRQ pin for NRF24 (leave defined if wired)
#ifndef RADIO_IRQ_PIN
#define RADIO_IRQ_PIN 43
#endif

// I2C LCD (16x1 büyük font modül; çoğu 16x1 aslında 8x2 adreslemeye sahiptir)
#ifndef LCD_ENABLED
#define LCD_ENABLED 1
#endif
#ifndef LCD_I2C_ADDR
#define LCD_I2C_ADDR 0x3F
#endif
#ifndef LCD_COLS
#define LCD_COLS 20
#endif
#ifndef LCD_ROWS
#define LCD_ROWS 4
#endif
#ifndef LCD_16X1_SPLIT_ROW
#define LCD_16X1_SPLIT_ROW 1  // 1: use row split (0,1), 0: use position split (0-7, 8-15)
#endif

// If only ONE LCD is detected on I2C and it looks like a standard 16x2, auto-promote it to 16x2 mode.
// This prevents "2x8" look when a 16x2 screen is configured as 16x1.
#ifndef LCD_AUTO_PROMOTE_16X2_IF_SINGLE
#define LCD_AUTO_PROMOTE_16X2_IF_SINGLE 1
#endif

// Single primary I2C LCD (20x4) is expected in this build.

// RFID (MFRC522 - SPI)
#ifndef RFID_ENABLED
#define RFID_ENABLED 1
#endif
#ifndef RFID_SS_PIN
#define RFID_SS_PIN 53
#endif
#ifndef RFID_RST_PIN
#define RFID_RST_PIN 49
#endif
// When the same tag remains present, allow re-emitting an event after this interval (ms)
#ifndef RFID_REPEAT_MS
#define RFID_REPEAT_MS 2000
#endif

// HC-SR04 Ultrasonic
#ifndef ULTRA_ENABLED
#define ULTRA_ENABLED 1
#endif
#ifndef ULTRA_TRIG_PIN
#define ULTRA_TRIG_PIN 4
#endif
#ifndef ULTRA_ECHO_PIN
#define ULTRA_ECHO_PIN 5
#endif
#ifndef ULTRA_MEASURE_INTERVAL_MS
#define ULTRA_MEASURE_INTERVAL_MS 50
#endif
#ifndef AVOID_ENABLE_DEFAULT
#define AVOID_ENABLE_DEFAULT 1
#endif
#ifndef AVOID_DISTANCE_CM
#define AVOID_DISTANCE_CM 25.0f
#endif

// When closer than this (cm), play a sustained/continuous warning tone
#ifndef AVOID_CONTINUOUS_CM
#define AVOID_CONTINUOUS_CM 8.0f
#endif
#ifndef AVOID_REVERSE_SPEED
// Sit/skate modunda engelden kaçma için geri hız (steps/s)
#define AVOID_REVERSE_SPEED -400.0f
#endif

// Dual laser pointers (cross lasers)
#ifndef LASER_ENABLED
#define LASER_ENABLED 1
#endif
#ifndef LASER1_PIN
#define LASER1_PIN 6
#endif
#ifndef LASER2_PIN
#define LASER2_PIN 7
#endif
#ifndef LASER_ACTIVE_HIGH
#define LASER_ACTIVE_HIGH 1  // 1: HIGH opens laser, 0: LOW opens laser
#endif

// =====================
// IR Remote (optional)
// =====================
#ifndef IR_ENABLED
#define IR_ENABLED 1
#endif
#ifndef IR_PIN
// IR receiver OUT pin
#define IR_PIN 23
#endif
// =====================
// Dual Buzzer (optional)
// =====================
// Two physical buzzers: one loud, one quiet.
#ifndef BUZZER_ENABLED
#define BUZZER_ENABLED 1
#endif
#ifndef CUTE_BUZZER_LIB_ENABLED
// 1: use CuteBuzzerSounds library if installed, 0: use internal fallback sounds.
#define CUTE_BUZZER_LIB_ENABLED 0
#endif
#ifndef BUZZER_LOUD_PIN
#define BUZZER_LOUD_PIN 2 // Hardware mapping: loud -> pin 2
#endif
#ifndef BUZZER_QUIET_PIN
#define BUZZER_QUIET_PIN 3 // Hardware mapping: quiet -> pin 3
#endif
#ifndef BUZZER_USE_TONE
// 1: use tone() with freq; 0: simple digital on/off
#define BUZZER_USE_TONE 1
#endif

// On AVR, IRremote and tone() can share timers; this may break IR reception after a beep.
// Default: if IR is enabled, avoid tone() and use non-blocking digital beep instead.
// By default allow tone() even when IR is enabled. If you experience IR
// reception issues while tone() runs, set this to 1 to disable tone() and
// fall back to simple digital toggles. Re-initialization of IR after tone()
// is enabled via BUZZER_REINIT_IR_AFTER_TONE.
#ifndef BUZZER_DISABLE_TONE_WHEN_IR
#define BUZZER_DISABLE_TONE_WHEN_IR 0
#endif

// If tone() is used while IR is enabled (BUZZER_DISABLE_TONE_WHEN_IR=0),
// AVR timers can leave IRremote in a stuck state. Re-initialize IR receiver
// shortly after tone() finishes to resume IR decoding.
#ifndef BUZZER_REINIT_IR_AFTER_TONE
#define BUZZER_REINIT_IR_AFTER_TONE 1
#endif

#ifndef BOOT_BEEP
// 1: play short beep on boot
#define BOOT_BEEP 0
#endif

// Boot status screen
#ifndef BOOT_STATUS_ENABLED
#define BOOT_STATUS_ENABLED 1
#endif
#ifndef BOOT_STATUS_STEP_MS
// Increase step time slightly so boot scanning messages are readable on LCD.
#define BOOT_STATUS_STEP_MS 800
#endif

// Boot UI / diagnostics
#ifndef BOOT_UI_ENABLED
#define BOOT_UI_ENABLED 1
#endif
#ifndef BOOT_SPLASH_MS
#define BOOT_SPLASH_MS 450
#endif
#ifndef BOOT_STATUS_OK_MS
#define BOOT_STATUS_OK_MS 250
#endif
#ifndef BOOT_STATUS_FAIL_MS
#define BOOT_STATUS_FAIL_MS 1200
#endif


// =====================
// Servos over I2C (PCA9685)
// =====================
#ifndef SERVO_USE_PCA9685
#define SERVO_USE_PCA9685 1   // 1: use PCA9685 over I2C; 0: use Arduino Servo pins
#endif
#ifndef PCA9685_ADDR
#define PCA9685_ADDR 0x40
#endif
#ifndef SERVO_FREQ_HZ
#define SERVO_FREQ_HZ 50
#endif
// Angle to pulse width mapping (typical analog servo)
#ifndef SERVO_MIN_US
#define SERVO_MIN_US 500
#endif
#ifndef SERVO_MAX_US
#define SERVO_MAX_US 2500
#endif

// NeoPixel (WS2812) removed from this firmware build.

// =====================
// Hall encoder (optional)
// =====================
#ifndef HALL_ENCODER_ENABLED
#define HALL_ENCODER_ENABLED 1
#endif
#ifndef HALL_PIN_0
#define HALL_PIN_0 30
#endif
#ifndef HALL_PIN_1
#define HALL_PIN_1 31
#endif
#ifndef HALL_DEBOUNCE_MS
#define HALL_DEBOUNCE_MS 6
#endif

// Hall sensörleri için manyet/pulse sayısı (varsayılan)
// Varsayılan: tek manyet (1). Eğer her tekerde farklı sayıda manyet varsa
// runtime calibrate ile teker başına çarpanı belirleyebilirsiniz.
// Default pulses-per-rev: set to 4 magnets per wheel
#ifndef HALL_PULSES_PER_REV
#define HALL_PULSES_PER_REV 4
#endif

// Per-teker alternatif makrolar (isteğe bağlı override)
#ifndef HALL_PULSES_PER_REV_0
#define HALL_PULSES_PER_REV_0 HALL_PULSES_PER_REV
#endif
#ifndef HALL_PULSES_PER_REV_1
#define HALL_PULSES_PER_REV_1 HALL_PULSES_PER_REV
#endif

// Analog Hall sensörü kullanımı için ayarlar
#ifndef HALL_ANALOG_MODE
// 0: digitalRead() (Recommended), 1: analogRead() + threshold
#define HALL_ANALOG_MODE 0
#endif
#ifndef HALL_ANALOG_THRESHOLD
// Analog eşik (0..1023). Sensörün çıkışına göre ayarlayın (varsayılan 512).
#define HALL_ANALOG_THRESHOLD 512
#endif

// =====================
// DS18B20 / OneWire temperature sensors
// Single-wire bus: connect all DS18B20 devices to this pin (parasite power NOT required/recommended)
#ifndef DS18_ENABLED
#define DS18_ENABLED 1
#endif
#ifndef DS18_PIN
#define DS18_PIN 22
#endif
#ifndef DS18_POLL_MS
#define DS18_POLL_MS 5000
#endif
// Overheat threshold in Celsius (default)
#ifndef DS18_OVERHEAT_C
#define DS18_OVERHEAT_C 60.0f
#endif
// Expected number of DS18 devices attached (used for reporting). Default 6 as requested.
#ifndef DS18_SENSOR_COUNT
#define DS18_SENSOR_COUNT 8
#endif

#endif // ROBOT_CONFIG_H