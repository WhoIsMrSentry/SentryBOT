#ifndef ROBOT_CONFIG_H
#define ROBOT_CONFIG_H
#include <Arduino.h>

// Board serial
#define ROBOT_SERIAL_BAUD 115200
// Select serial port (Serial for USB, or Serial1 for RPi UART)
#ifndef SERIAL_IO
#define SERIAL_IO Serial
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
#define PIN_STEPPER1_STEP 10
#define PIN_STEPPER1_DIR  11
#define PIN_STEPPER2_STEP 12
#define PIN_STEPPER2_DIR  13
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

// EEPROM (kalibrasyon) - basit layout
#define EEPROM_MAGIC 0x42
#define EEPROM_ADDR_MAGIC   0
#define EEPROM_ADDR_IMU_OFF 1   // float2: offPitch, offRoll (8 byte)

// =====================
// Peripherals (optional)
// =====================

// I2C LCD (16x1 büyük font modül; çoğu 16x1 aslında 8x2 adreslemeye sahiptir)
#ifndef LCD_ENABLED
#define LCD_ENABLED 1
#endif
#ifndef LCD_I2C_ADDR
#define LCD_I2C_ADDR 0x27
#endif
#ifndef LCD_COLS
#define LCD_COLS 16
#endif
#ifndef LCD_ROWS
#define LCD_ROWS 1
#endif
#ifndef LCD_16X1_SPLIT_ROW
#define LCD_16X1_SPLIT_ROW 1  // 1: use row split (0,1), 0: use position split (0-7, 8-15)
#endif

// RFID (MFRC522 - SPI)
#ifndef RFID_ENABLED
#define RFID_ENABLED 1
#endif
#ifndef RFID_SS_PIN
// MEGA: 53 donanımsal SS; RC522 için ayrı SS kullanılabilir
#define RFID_SS_PIN 53
#endif
#ifndef RFID_RST_PIN
#define RFID_RST_PIN 49
#endif

// HC-SR04 Ultrasonic
#ifndef ULTRA_ENABLED
#define ULTRA_ENABLED 1
#endif
#ifndef ULTRA_TRIG_PIN
#define ULTRA_TRIG_PIN 22
#endif
#ifndef ULTRA_ECHO_PIN
#define ULTRA_ECHO_PIN 23
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
#ifndef AVOID_REVERSE_SPEED
// Sit/skate modunda engelden kaçma için geri hız (steps/s)
#define AVOID_REVERSE_SPEED -400.0f
#endif

// Dual laser pointers (cross lasers)
#ifndef LASER_ENABLED
#define LASER_ENABLED 1
#endif
#ifndef LASER1_PIN
#define LASER1_PIN 24
#endif
#ifndef LASER2_PIN
#define LASER2_PIN 25
#endif
#ifndef LASER_ACTIVE_HIGH
#define LASER_ACTIVE_HIGH 1  // 1: HIGH opens laser, 0: LOW opens laser
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

#endif // ROBOT_CONFIG_H