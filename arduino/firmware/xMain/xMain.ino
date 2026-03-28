#include <Arduino.h>
#include "xConfig.h"
#include "xProtocol.h"
#include "xRobot.h"
#include <EEPROM.h>
#include "xPeripherals.h"
#include "peripherals/xEbyteRadio.h"
#include "actuators/xNemaController.h"

#include "app/xLcdHub.h"
#include "app/xIrMenuController.h"
#include "app/xCommands.h"
#include "app/xCuteBuzzer.h"

Robot robot;
unsigned long lastHeartbeatMs = 0;
bool g_linkAlive = false;
bool g_linkEverAlive = false;
bool telemetryOn = false;
unsigned long telemetryInterval = 100;
unsigned long lastTelemetryMs = 0;
// Song queue

// Song queue (simple ring) with compact IDs to avoid String heap churn.
enum SongId : uint8_t {
  SONG_NONE = 0,
  SONG_WALLE,
  SONG_BB8_1,
  SONG_BB8_2,
  SONG_BB8_3,
};

const int SONG_QUEUE_CAP = 8;
uint8_t g_songQueue[SONG_QUEUE_CAP];
int g_songQueueStart = 0;
int g_songQueueCount = 0;

static inline const char* songNameFromId(uint8_t id){
  switch (id){
    case SONG_WALLE: return "walle";
    case SONG_BB8_1: return "bb8_1";
    case SONG_BB8_2: return "bb8_2";
    case SONG_BB8_3: return "bb8_3";
    default: return nullptr;
  }
}

static inline void enqueueSong(uint8_t songId){
  if (songId == SONG_NONE) return;
  if (g_songQueueCount >= SONG_QUEUE_CAP) return;
  int idx = (g_songQueueStart + g_songQueueCount) % SONG_QUEUE_CAP;
  g_songQueue[idx] = songId;
  g_songQueueCount++;
}

static inline void processSongQueue(){
  if (g_songQueueCount == 0) return;
  // g_song is global BuzzerSongPlayer; check isPlaying()
  if (!g_song.isPlaying()){
    uint8_t songId = g_songQueue[g_songQueueStart];
    g_songQueueStart = (g_songQueueStart + 1) % SONG_QUEUE_CAP;
    g_songQueueCount--;
    const char* songName = songNameFromId(songId);
    if (songName != nullptr) g_song.play(songName, g_buzzerDefaultOut);
  }
}

// Status LED mode (managed in loop)
volatile uint8_t g_statusLedMode = STATUS_LED_OFF;
unsigned long g_statusLedLastMs = 0;
bool g_statusLedState = false;

// Proximity beep state for HC-SR04 parking-like feedback
unsigned long g_lastProxBeepMs = 0;
bool g_proxContinuousOn = false;

#if RFID_ENABLED
RfidReader g_rfid;
String g_lastRfid;
#endif
String g_lastSpeech;
#if LCD_ENABLED
LcdDisplay g_lcd1;
  bool g_lcd1Ok = false;
LcdStatus g_lcdStatus;
#endif
#if ULTRA_ENABLED
Ultrasonic g_ultra;
float g_ultraCm = NAN;
bool g_avoidEnable = AVOID_ENABLE_DEFAULT;
#endif
#if LASER_ENABLED
LaserPair g_lasers;
#endif
#if DS18_ENABLED
Ds18b20Manager g_ds18;
#endif
#if BUZZER_ENABLED
BuzzerPair g_buzzer;
BuzzerSongPlayer g_song;
BuzzerOut g_buzzerDefaultOut = BUZZER_OUT_LOUD;
#if 1
// Runtime flag to enable both buzzers simultaneously (default: false)
bool g_buzzerBothEnabled = false;
#endif
#if BUZZER_ENABLED
// Runtime adjustable frequencies for loud and quiet buzzers (persisted to EEPROM)
uint16_t g_buzzerFreqLoud = 1500;
uint16_t g_buzzerFreqQuiet = 1200;
#endif
#endif
#if IR_ENABLED
IrKeyReader g_ir;
#endif

#if IR_ENABLED
IrMenuController g_irMenu;
void pushAlert(const String &msg) { g_irMenu.addAlert(msg); }
#else
void pushAlert(const String &msg) { /* silence */ }
#endif

#if HALL_ENCODER_ENABLED
HallEncoder g_hall0;
HallEncoder g_hall1;
#endif

static String g_rxLine;
static String g_irKey;
static String g_lcdLineTmp;

static inline void printJsonEscaped(const String &s){
  for (size_t i = 0; i < s.length(); ++i){
    char c = s[i];
    switch (c){
      case '"': SERIAL_IO.print(F("\\\"")); break;
      case '\\': SERIAL_IO.print(F("\\\\")); break;
      case '\n': SERIAL_IO.print(F("\\n")); break;
      case '\r': SERIAL_IO.print(F("\\r")); break;
      case '\t': SERIAL_IO.print(F("\\t")); break;
      default: SERIAL_IO.print(c); break;
    }
  }
}

static inline bool isOwnerUid(const char *uid){
  // "F3A186A5" (8 chars)
  return uid[0]=='F' && uid[1]=='3' && uid[2]=='A' && uid[3]=='1' && uid[4]=='8' && uid[5]=='6' && uid[6]=='A' && uid[7]=='5' && uid[8]=='\0';
}

static inline void printTelemetryJson(){
  SERIAL_IO.print(F("{\"ok\":true,\"telemetry\":true,\"pitch\":"));
  SERIAL_IO.print(robot.imu.getPitch(), 2);
  SERIAL_IO.print(F(",\"roll\":"));
  SERIAL_IO.print(robot.imu.getRoll(), 2);
  SERIAL_IO.print(F(",\"pose\":["));
  for (int i = 0; i < SERVO_COUNT_TOTAL; ++i){
    if (i) SERIAL_IO.print(',');
    SERIAL_IO.print((int)robot.servos.get(i));
  }
  SERIAL_IO.print(F("],\"stepper_pos\":["));
  SERIAL_IO.print(robot.steppers.pos1());
  SERIAL_IO.print(',');
  SERIAL_IO.print(robot.steppers.pos2());
  SERIAL_IO.print(']');
#if RFID_ENABLED
  SERIAL_IO.print(F(",\"rfid\":\""));
  printJsonEscaped(g_lastRfid);
  SERIAL_IO.print('"');
#endif
#if ULTRA_ENABLED
  SERIAL_IO.print(F(",\"ultra_cm\":"));
  if (isnan(g_ultraCm)) SERIAL_IO.print(F("null"));
  else SERIAL_IO.print(g_ultraCm, 1);
#endif
  SERIAL_IO.println('}');
}

void setup(){
  SERIAL_IO.begin(ROBOT_SERIAL_BAUD);
  SERIAL_IO.println(F("{\"info\":\"boot_start\"}"));
  g_rxLine.reserve(128);
  g_irKey.reserve(12);
  g_lcdLineTmp.reserve(22);
#if RFID_ENABLED
  g_lastRfid.reserve(16);
#endif
  g_lastSpeech.reserve(32);
  // Status LED pin
  pinMode(PIN_STATUS_LED, OUTPUT);
  g_statusLedMode = STATUS_LED_BLINK_SLOW; // boot activity
  robot.begin();
  // Initialize and attach hall encoders (if enabled) after steppers are started
#if HALL_ENCODER_ENABLED
  // Load per-wheel pulses-per-rev from EEPROM if present, otherwise use config defaults
  uint16_t ppr0 = HALL_PULSES_PER_REV_0;
  uint16_t ppr1 = HALL_PULSES_PER_REV_1;
  if (EEPROM.read(EEPROM_ADDR_HALL_MAGIC) == EEPROM_HALL_MAGIC){
    uint16_t e0=0, e1=0;
    EEPROM.get(EEPROM_ADDR_HALL_PPR_0, e0);
    EEPROM.get(EEPROM_ADDR_HALL_PPR_1, e1);
    if (e0 > 0 && e0 < 100) ppr0 = e0;
    if (e1 > 0 && e1 < 100) ppr1 = e1;
  }
  // Begin hall encoders in analog mode if configured
  g_hall0.begin(HALL_PIN_0, ppr0, (bool)HALL_ANALOG_MODE, HALL_ANALOG_THRESHOLD);
  g_hall1.begin(HALL_PIN_1, ppr1, (bool)HALL_ANALOG_MODE, HALL_ANALOG_THRESHOLD);
  robot.steppers.attachHallEncoders(&g_hall0, &g_hall1);

  // Auto-load PID gains from EEPROM for each motor (if present)
  bool l0 = robot.steppers.loadPidFromEeprom(0);
  bool l1 = robot.steppers.loadPidFromEeprom(1);
  if (l0 || l1) Protocol::sendOk("pid_loaded");
#endif
  // Initialize EBYTE radio (nRF24L01 compatible) and NEMA controller
  #if EBYTE_ENABLED && defined(RADIO_CE_PIN) && defined(RADIO_CSN_PIN)
  g_ebyteRadio.begin(RADIO_CE_PIN, RADIO_CSN_PIN, 100);
#endif
  // Initialize NEMA controller
  g_nema.begin();
  // Auto-load IMU offsets if present
  if (EEPROM.read(EEPROM_ADDR_MAGIC)==EEPROM_MAGIC){ float p,r; EEPROM.get(EEPROM_ADDR_IMU_OFF,p); EEPROM.get(EEPROM_ADDR_IMU_OFF+sizeof(float),r); robot.imu.setOffsets(p,r); }
  // Load persisted buzzer frequencies if present
  #if BUZZER_ENABLED
  if (EEPROM.read(EEPROM_ADDR_BUZZER_FREQ_MAGIC) == EEPROM_BUZZER_MAGIC){
    uint16_t vfL = 0; uint16_t vfQ = 0;
    EEPROM.get(EEPROM_ADDR_BUZZER_FREQ_LOUD, vfL);
    EEPROM.get(EEPROM_ADDR_BUZZER_FREQ_QUIET, vfQ);
    if (vfL >= 200 && vfL <= 4000) g_buzzerFreqLoud = vfL;
    if (vfQ >= 200 && vfQ <= 4000) g_buzzerFreqQuiet = vfQ;
  }
  #endif
  Protocol::sendOk(F("ready"));
  // Indicate ready
  g_statusLedMode = STATUS_LED_SOLID;
#if LCD_ENABLED
  Wire.begin();
#if defined(ARDUINO_ARCH_AVR)
  // Keep I2C from hanging forever but do not hard-reset MCU on timeout.
  Wire.setWireTimeout(25000, false);
#endif
  uint8_t lcd1Addr = LCD_I2C_ADDR;

  // Auto-detect LCD1 address: try configured value first, otherwise scan common I2C addresses.
  bool p1 = false;
  if (i2cDevicePresent(lcd1Addr)){
    p1 = true;
  } else {
    // Common addresses for I2C LCD backpacks and modules
    const uint8_t scanCandidates[] = {0x27, 0x3F, 0x3E, 0x26, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25};
    for (size_t si = 0; si < sizeof(scanCandidates); ++si){
      uint8_t a = scanCandidates[si];
      if (i2cDevicePresent(a)){
        lcd1Addr = a;
        p1 = true;
        break;
      }
    }
  }
  g_lcd1Ok = p1;
  // Auto-promote: if only one LCD exists, prefer treating it as 16x2 (prevents 2x8 split look on 16x2 modules).
  bool onlyOne = p1;

  if (p1){
    uint8_t cols = LCD_COLS;
    uint8_t rows = LCD_ROWS;
    bool split = (bool)LCD_16X1_SPLIT_ROW;
    if (LCD_AUTO_PROMOTE_16X2_IF_SINGLE && onlyOne && cols == 16 && rows == 1){
      rows = 2;
      split = false;
    }
    g_lcd1.begin(lcd1Addr, cols, rows, split);
  }


  // LCD yoksa firmware çalışmaya devam eder; sadece LCD yazımı atlanır.
  g_lcdStatus.begin("", 0);
  g_irMenu.reset();
  g_irMenu.showHome();

    if (BOOT_STATUS_ENABLED && lcdHubAny()){
    bootUiStep(F("SentryBOT"), (const __FlashStringHelper*)F("BOOT"), BOOT_SPLASH_MS);

    // LCDs
    bootInfo("lcd1", g_lcd1Ok);
    bootUiStep(F("LCD1"), g_lcd1Ok ? (const __FlashStringHelper*)F("OK") : (const __FlashStringHelper*)F("MISSING"), g_lcd1Ok ? BOOT_STATUS_OK_MS : BOOT_STATUS_FAIL_MS);


    // I2C modules
    // Check both common MPU6050 addresses (0x68 and 0x69) because AD0 pin
    // on some modules may be pulled high (0x69).
    bool imuOk = i2cDevicePresent(IMU_I2C_ADDR) || i2cDevicePresent(0x69);
    bootInfo("imu", imuOk);
    bootUiStep(F("IMU"), imuOk ? (const __FlashStringHelper*)F("OK") : (const __FlashStringHelper*)F("MISSING"), imuOk ? BOOT_STATUS_OK_MS : BOOT_STATUS_FAIL_MS);

  #if SERVO_USE_PCA9685
    bool pcaOk = i2cDevicePresent(PCA9685_ADDR);
    bootInfo("pca9685", pcaOk);
    bootUiStep(F("SERVO"), pcaOk ? (const __FlashStringHelper*)F("PCA9685 OK") : (const __FlashStringHelper*)F("PCA9685 MISSING"), pcaOk ? BOOT_STATUS_OK_MS : BOOT_STATUS_FAIL_MS);
  #else
    bootInfo("servo_driver", true);
    bootUiStep(F("SERVO"), (const __FlashStringHelper*)F("DIRECT PINS"), BOOT_STATUS_OK_MS);
  #endif

    // Compile-time features (to give a bit of "liveliness")
    String feat = String("") + (IR_ENABLED?"IR ":"") + (RFID_ENABLED?"RFID ":"") + (ULTRA_ENABLED?"ULTRA ":"") + (LASER_ENABLED?"LASER ":"");
    if (feat.length() > 0) bootUiStep(F("FEATURES"), feat, BOOT_STATUS_STEP_MS);


    }
#endif
#if RFID_ENABLED
  g_rfid.begin(RFID_SS_PIN, RFID_RST_PIN);
#endif
#if ULTRA_ENABLED
  g_ultra.begin(ULTRA_TRIG_PIN, ULTRA_ECHO_PIN);
#endif
#if LASER_ENABLED
  g_lasers.begin(LASER1_PIN, LASER2_PIN);
#endif
#if BUZZER_ENABLED
  g_buzzer.begin(BUZZER_LOUD_PIN, BUZZER_QUIET_PIN);
  g_song.begin(&g_buzzer);
  g_song.setDefaultOut(g_buzzerDefaultOut);
  cuteBuzzerInit();
#if BOOT_BEEP
  // Boot beep uses LOUD at test freq
  g_buzzer.beepOn(BUZZER_OUT_LOUD, g_buzzerFreqLoud, 50);
#endif
#endif
#if DS18_ENABLED
  // Start DS18B20 OneWire sensors (all devices on single pin)
  g_ds18.begin(DS18_PIN);
#endif
#if IR_ENABLED
  g_ir.begin(IR_PIN);
  #if LCD_ENABLED
  // IR menü olayları ana LCD'de gösterilsin
  g_irMenu.setLcdPrint([](const String &top, const String &bottom){ g_lcdStatus.showTo(LCD_TGT_1, top, bottom, true); });
#endif
  g_irMenu.reset();
#endif
#if BOOT_CALIBRATION_PROMPT
  unsigned long t0 = millis();
  SERIAL_IO.println(F("{\"info\":\"press 'c' + Enter in 2s to calibrate\"}"));
  while (millis() - t0 < 2000) {
    if (SERIAL_IO.available()){
      String ln = SERIAL_IO.readStringUntil('\n'); ln.trim();
      if (ln.equalsIgnoreCase("c") || ln.indexOf("\"cmd\":\"calibrate\"")>=0){
        robot.calibrateNeutral();
        Protocol::sendOk("boot_calibrated");
      }
      break;
    }
    delay(5);
  }
#endif
}

void loop(){
  g_irMenu.countLoop();
  if (Protocol::readLine(SERIAL_IO, g_rxLine)) handleJson(g_rxLine);
  robot.update();
    // Peripherals polling
  #if RFID_ENABLED
    if (g_rfid.poll()){
      g_irMenu.recordRfid();
      g_lastRfid = g_rfid.lastUid();
      SERIAL_IO.print(F("{\"ok\":true,\"event\":\"rfid\",\"uid\":\""));
      printJsonEscaped(g_lastRfid);
      SERIAL_IO.println(F("\"}"));
  #if LCD_ENABLED
      // Show brief RFID on main status LCD (LCD1)
      char tail[9];
      size_t rlen = g_lastRfid.length();
      size_t start = (rlen > 8) ? (rlen - 8) : 0;
      uint8_t ti = 0;
      for (size_t p = start; p < rlen && ti < 8; ++p) tail[ti++] = g_lastRfid[p];
      tail[ti] = '\0';
      g_lcdLineTmp = tail;
      g_lcdStatus.showTo(LCD_TGT_1, "RFID", g_lcdLineTmp, true);

      // Normalize UID (remove non-alnum, uppercase)
      char norm[17];
      uint8_t ni = 0;
      for (size_t _i = 0; _i < g_lastRfid.length(); ++_i){
        char c = g_lastRfid[_i];
        if ((c >= '0' && c <= '9') || (c >= 'A' && c <= 'F') || (c >= 'a' && c <= 'f')){
          if (c >= 'a' && c <= 'f') c = c - ('a' - 'A');
          if (ni < sizeof(norm) - 1) norm[ni++] = c;
        }
      }
      norm[ni] = '\0';

      // Owner UID (uppercase, no separators)
      if (isOwnerUid(norm)){
        // Greet owner on LCD1
        g_lcdStatus.showTo(LCD_TGT_1, "Merhaba", "Sahip", true);
        playCuteSound(CUTE_SUPER_HAPPY, true);
        // Enqueue sequence: walle then three bb8 variants
        enqueueSong(SONG_WALLE);
        enqueueSong(SONG_BB8_1);
        enqueueSong(SONG_BB8_2);
        enqueueSong(SONG_BB8_3);
      }
  #endif
    }
  #endif
  #if ULTRA_ENABLED
    if (g_ultra.measureIfDue(ULTRA_MEASURE_INTERVAL_MS)){
      g_ultraCm = g_ultra.lastCm();
    }
    if (g_avoidEnable && robot.getMode()==MODE_SKATE){
      if (!isnan(g_ultraCm) && g_ultraCm>0 && g_ultraCm < AVOID_DISTANCE_CM){
        robot.setDriveCmd(AVOID_REVERSE_SPEED);
  #if LCD_ENABLED
      char cmBuf[12];
      ltoa((long)g_ultraCm, cmBuf, 10);
      g_lcdLineTmp = cmBuf;
      g_lcdLineTmp += "cm";
      g_lcdStatus.show("AVOID", g_lcdLineTmp);
      pushAlert(F("OBSTACLE DETECTED"));
  #endif
  // Song queue processing lives in the main BUZZER section below.
      }
    }
#if ULTRA_ENABLED && BUZZER_ENABLED
    // Parking-style proximity beeps while sitting in avoid-mode
    if (g_avoidEnable && robot.getMode()==MODE_SKATE){
      if (!isnan(g_ultraCm) && g_ultraCm>0 && g_ultraCm < AVOID_DISTANCE_CM){
        unsigned long nowp = millis();
        if (g_ultraCm <= AVOID_CONTINUOUS_CM){
          // Very close: start a sustained/continuous tone
          if (!g_proxContinuousOn){
            if (g_buzzerBothEnabled){
              g_buzzer.beepOn(BUZZER_OUT_LOUD, g_buzzerFreqLoud, 0);
              g_buzzer.beepOn(BUZZER_OUT_QUIET, g_buzzerFreqQuiet, 0);
            } else {
              uint16_t f = (g_buzzerDefaultOut==BUZZER_OUT_LOUD)?g_buzzerFreqLoud:g_buzzerFreqQuiet;
              g_buzzer.beepOn(g_buzzerDefaultOut, f, 0);
            }
            g_proxContinuousOn = true;
          }
        } else {
          // PROPORTIONAL parking beeps
          // Scale linearly from 60ms (at 8cm) to 800ms (at 25cm)
          unsigned long interval = (unsigned long)((g_ultraCm - AVOID_CONTINUOUS_CM) * 43.5f + 60.0f);
          interval = constrain(interval, 50, 1000);

          if (nowp - g_lastProxBeepMs >= interval){
            g_lastProxBeepMs = nowp;
            if (g_buzzerBothEnabled){
              g_buzzer.beepOn(BUZZER_OUT_LOUD, g_buzzerFreqLoud, 40);
              g_buzzer.beepOn(BUZZER_OUT_QUIET, g_buzzerFreqQuiet, 40);
            } else {
              uint16_t f = (g_buzzerDefaultOut==BUZZER_OUT_LOUD)?g_buzzerFreqLoud:g_buzzerFreqQuiet;
              g_buzzer.beepOn(g_buzzerDefaultOut, f, 40);
            }
          }
          if (g_proxContinuousOn){
            g_buzzer.stop();
            g_proxContinuousOn = false;
          }
        }
      } else {
        // If ultrasonic no longer in range/valid, ensure sustained tone is stopped
        if (g_proxContinuousOn){
          g_buzzer.stop();
          g_proxContinuousOn = false;
        }
      }
    }
#endif
  #endif

#if IR_ENABLED
  if (g_ir.poll(g_irKey)){
    g_irMenu.onKey(g_irKey, robot);
  }
  g_irMenu.tick(robot);
#endif

#if LCD_ENABLED
  g_lcdStatus.tick();
#endif

#if BUZZER_ENABLED
  // First, allow queued songs to start if no song currently playing
  processSongQueue();
  g_song.update();
  g_buzzer.update();
#endif
  
  // Heartbeat timeout safety
  if (HEARTBEAT_TIMEOUT_MS > 0){
    bool linkNow = (millis() - lastHeartbeatMs) <= HEARTBEAT_TIMEOUT_MS;
    if (linkNow && !g_linkAlive){
      g_linkAlive = true;
      g_linkEverAlive = true;
      playCuteSound(CUTE_CONNECTION, true);
    } else if (!linkNow && g_linkAlive && g_linkEverAlive){
      g_linkAlive = false;
      playCuteSound(CUTE_DISCONNECTION, true);
    }
  }
  if (HEARTBEAT_TIMEOUT_MS>0 && (millis() - lastHeartbeatMs > HEARTBEAT_TIMEOUT_MS)){
    robot.estop();
  }
  // Poll radio and update NEMA controller
  #if EBYTE_ENABLED
  g_ebyteRadio.poll();
  #endif
  g_nema.update();
  #if DS18_ENABLED
  g_ds18.update();
  #endif
  #if HALL_ENCODER_ENABLED
  g_hall0.update();
  g_hall1.update();
  #endif
  // Telemetry periodic output
  if (telemetryOn && millis() - lastTelemetryMs >= telemetryInterval){
    lastTelemetryMs = millis(); robot.imu.read();
    printTelemetryJson();
  }
  // periodic maintenance for neopixel request retries/acks
  // Status LED handling
  {
    unsigned long nowLed = millis();
    switch (g_statusLedMode){
      case STATUS_LED_SOLID:
        if (!g_statusLedState){ digitalWrite(PIN_STATUS_LED, HIGH); g_statusLedState = true; }
        break;
      case STATUS_LED_OFF:
        if (g_statusLedState){ digitalWrite(PIN_STATUS_LED, LOW); g_statusLedState = false; }
        break;
      case STATUS_LED_BLINK_SLOW:
        if ((long)(nowLed - g_statusLedLastMs) >= 800){ g_statusLedLastMs = nowLed; g_statusLedState = !g_statusLedState; digitalWrite(PIN_STATUS_LED, g_statusLedState?HIGH:LOW); }
        break;
      case STATUS_LED_BLINK_FAST:
        if ((long)(nowLed - g_statusLedLastMs) >= 200){ g_statusLedLastMs = nowLed; g_statusLedState = !g_statusLedState; digitalWrite(PIN_STATUS_LED, g_statusLedState?HIGH:LOW); }
        break;
      default: break;
    }
  }
  neopixelTick();
}
