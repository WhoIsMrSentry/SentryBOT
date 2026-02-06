#ifndef ROBOT_CONFIG_H
#define ROBOT_CONFIG_H
#include <Arduino.h>

// Board serial
#define ROBOT_SERIAL_BAUD 115200
// Select serial port (Serial for USB, or Serial1/Serial3 for other boards / RPi UART)
// Default selection: prefer the first hardware UART on boards that expose it
// (e.g. Arduino Mega family) so Raspberry Pi can connect to `Serial1` safely.
// You can still override by defining `SERIAL_IO` before including this header.
#ifndef SERIAL_IO
	// Detect common Mega2560/MEGA variants and map to Serial1 (RX/TX on pins 19/18)
#if defined(ARDUINO_AVR_MEGA2560) || defined(ARDUINO_AVR_MEGA) || defined(__AVR_ATmega2560__)
#define SERIAL_IO Serial1
#else
#define SERIAL_IO Serial
#endif
#endif

// Servo counts
#define SERVO_COUNT_TOTAL 8 // 6 leg (L/R hip, knee, ankle) + 2 head (tilt, pan)
#define SERVO_LEG_COUNT 6
#define SERVO_HEAD_COUNT 2

// Stepper counts
#define STEPPER_COUNT 2 // Ankle integrated skates

// Pins – adapt to your wiring
// Left leg 
#define PIN_L_HIP   15
#define PIN_L_KNEE  14
#define PIN_L_ANKLE 13
// Right leg 
#define PIN_R_HIP   0
#define PIN_R_KNEE  1
#define PIN_R_ANKLE 2
// Head: pan+tilt
#define PIN_HEAD_PAN  3
#define PIN_HEAD_TILT 12

// Stepper pins (moved to avoid servo overlap)
// Updated wiring: STEP/DIR pins
// Stepper1: STEP=10 DIR=9, Stepper2: STEP=8 DIR=7
#define PIN_STEPPER1_STEP 10
#define PIN_STEPPER1_DIR  9
#define PIN_STEPPER2_STEP 8
#define PIN_STEPPER2_DIR  7
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

// Leg geometry (mm)
#define THIGH_LEN 94.0f
#define SHIN_LEN  94.0f
#define FOOT_LEN  28.0f

// Mechanical offsets (deg)
#define OFFS_HIP    120.0f
#define OFFS_KNEE   90.0f
#define OFFS_ANKLE  85.0f

// Limits (deg)
#define HIP_MIN   0
#define HIP_MAX   180
#define KNEE_MIN  0
#define KNEE_MAX  180
#define ANKLE_MIN 20   // conservative to match right ankle min in original
#define ANKLE_MAX 165

// Head limits (from original)
#define HEAD_TILT_MIN 60
#define HEAD_TILT_MAX 120
#define HEAD_PAN_MIN  30
#define HEAD_PAN_MAX  150

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
static const uint8_t POSE_STAND[SERVO_COUNT_TOTAL] = {90,90,90, 90,90,90, 90,90};
static const uint8_t POSE_SIT[SERVO_COUNT_TOTAL]   = {90,110,60, 90,110,60, 90,90}; // simple folded legs

// Stepper skate balance PID (inverted pendulum)
#define SKATE_KP  18.0f   // speed per degree
#define SKATE_KI  0.0f
#define SKATE_KD  0.8f    // speed per (deg/s)
#define SKATE_SPEED_LIMIT 2000.0f // steps/s cap

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
#define MICROSTEP 16
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

// =====================
// Peripherals (optional)
// =====================

// I2C LCD (16x1 büyük font modül; çoğu 16x1 aslında 8x2 adreslemeye sahiptir)
#ifndef LCD_ENABLED
#define LCD_ENABLED 1
#endif
#ifndef LCD_I2C_ADDR
#define LCD_I2C_ADDR 0x3F
#endif
#ifndef LCD_COLS
#define LCD_COLS 16
#endif
#ifndef LCD_ROWS
#define LCD_ROWS 2
#endif
#ifndef LCD_16X1_SPLIT_ROW
#define LCD_16X1_SPLIT_ROW 1  // 1: use row split (0,1), 0: use position split (0-7, 8-15)
#endif

// LCD output routing defaults
// 0: AUTO (detected displays)
// 1: BOTH (write to both if present; else fallback to detected)
// 2: ONLY_1 (prefer LCD1; if missing, fallback to detected)
// 3: ONLY_2 (prefer LCD2; if missing, fallback to detected)
#ifndef LCD_ROUTE_DEFAULT
#define LCD_ROUTE_DEFAULT 1
#endif

// If only ONE LCD is detected on I2C and it looks like a standard 16x2, auto-promote it to 16x2 mode.
// This prevents "2x8" look when a 16x2 screen is configured as 16x1.
#ifndef LCD_AUTO_PROMOTE_16X2_IF_SINGLE
#define LCD_AUTO_PROMOTE_16X2_IF_SINGLE 1
#endif

// Optional second I2C LCD (typical 16x2). If one display is missing, firmware keeps running with the detected one.
#ifndef LCD2_ENABLED
#define LCD2_ENABLED 1
#endif
#ifndef LCD2_I2C_ADDR
#define LCD2_I2C_ADDR 0x27
#endif
#ifndef LCD2_COLS
#define LCD2_COLS 16
#endif
#ifndef LCD2_ROWS
#define LCD2_ROWS 2
#endif
#ifndef LCD2_16X1_SPLIT_ROW
#define LCD2_16X1_SPLIT_ROW 0
#endif

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
#define ULTRA_TRIG_PIN 6
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
#define LASER1_PIN 12
#endif
#ifndef LASER2_PIN
#define LASER2_PIN 11
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
#define IR_PIN 2
#endif
#ifndef IR_TOKEN_TIMEOUT_MS
// "*1" -> wait this long to commit token if no more digits come
#define IR_TOKEN_TIMEOUT_MS 900
#endif

// =====================
// Dual Buzzer (optional)
// =====================
// Two physical buzzers: one loud, one quiet.
#ifndef BUZZER_ENABLED
#define BUZZER_ENABLED 1
#endif
#ifndef BUZZER_LOUD_PIN
#define BUZZER_LOUD_PIN 3 // Hardware mapping: loud -> pin 3
#endif
#ifndef BUZZER_QUIET_PIN
#define BUZZER_QUIET_PIN 4 // Hardware mapping: quiet -> pin 4
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

// =====================
// NeoPixel (WS2812) defaults
// =====================
#ifndef NEOPIXEL_ENABLED
#define NEOPIXEL_ENABLED 0
#endif
#ifndef PIN_NEOPIXEL
#define PIN_NEOPIXEL 23
#endif
#ifndef NEO_NUM_LEDS
#define NEO_NUM_LEDS 23
#endif
#ifndef NEO_CONFIG
// User confirmed working with NEO_RGBW + NEO_KHZ800
#define NEO_CONFIG (NEO_RGBW + NEO_KHZ800)
#endif

#endif // ROBOT_CONFIG_H