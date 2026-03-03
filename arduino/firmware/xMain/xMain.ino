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
// Owner RFID cooldown and song queue
unsigned long g_lastOwnerRfidMs = 0;
String g_lastOwnerUid = "";
const unsigned long OWNER_RFID_COOLDOWN_MS = 5000UL;

// Song queue (simple ring)
const int SONG_QUEUE_CAP = 8;
String g_songQueue[SONG_QUEUE_CAP];
int g_songQueueStart = 0;
int g_songQueueCount = 0;

static inline void enqueueSong(const String &s){
  if (g_songQueueCount >= SONG_QUEUE_CAP) return;
  int idx = (g_songQueueStart + g_songQueueCount) % SONG_QUEUE_CAP;
  g_songQueue[idx] = s;
  g_songQueueCount++;
}

static inline void processSongQueue(){
  if (g_songQueueCount == 0) return;
  // g_song is global BuzzerSongPlayer; check isPlaying()
  if (!g_song.isPlaying()){
    String s = g_songQueue[g_songQueueStart];
    g_songQueueStart = (g_songQueueStart + 1) % SONG_QUEUE_CAP;
    g_songQueueCount--;
    g_song.play(s, g_buzzerDefaultOut);
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
  uint8_t g_lcdRouteMask = LCD_TGT_1;
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
#endif

#if HALL_ENCODER_ENABLED
HallEncoder g_hall0;
HallEncoder g_hall1;
#endif
// OLED instance
#if OLED_ENABLED
OledDisplay g_oled;
#endif

void setup(){
  SERIAL_IO.begin(ROBOT_SERIAL_BAUD);
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
#if defined(RADIO_CE_PIN) && defined(RADIO_CSN_PIN)
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
  Protocol::sendOk("ready");
  // Indicate ready
  g_statusLedMode = STATUS_LED_SOLID;
#if LCD_ENABLED
  Wire.begin();
#if defined(ARDUINO_ARCH_AVR)
  Wire.setWireTimeout(25000, true);
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


  // Default routing from config (still falls back to detected if requested target isn't present)
  // Route always to primary display in single-display firmware
  g_lcdRouteMask = LCD_TGT_1;

  // Eğer iki ekran da yoksa firmware yine çalışır; sadece LCD çıktısı no-op olur.
  g_lcdStatus.begin("READY", 3000);

  // Initialize OLED if present and show logo
#if OLED_ENABLED
  if (g_oled.begin(OLED_I2C_ADDR, 128, 64)){
    g_oled.showLogo();
    bootInfo("oled", true);
  } else {
    bootInfo("oled", false);
  }
#endif
    if (BOOT_STATUS_ENABLED && lcdHubAny()){
    bootUiStep("SentryBOT", "BOOT", BOOT_SPLASH_MS);

    // LCDs
    bootInfo("lcd1", g_lcd1Ok);
    bootUiStep("LCD1", g_lcd1Ok ? "OK" : "MISSING", g_lcd1Ok ? BOOT_STATUS_OK_MS : BOOT_STATUS_FAIL_MS);


    // I2C modules
    // Check both common MPU6050 addresses (0x68 and 0x69) because AD0 pin
    // on some modules may be pulled high (0x69).
    bool imuOk = i2cDevicePresent(IMU_I2C_ADDR) || i2cDevicePresent(0x69);
    bootInfo("imu", imuOk);
    bootUiStep("IMU", imuOk ? "OK" : "MISSING", imuOk ? BOOT_STATUS_OK_MS : BOOT_STATUS_FAIL_MS);

  #if SERVO_USE_PCA9685
    bool pcaOk = i2cDevicePresent(PCA9685_ADDR);
    bootInfo("pca9685", pcaOk);
    bootUiStep("SERVO", pcaOk ? "PCA9685 OK" : "PCA9685 MISSING", pcaOk ? BOOT_STATUS_OK_MS : BOOT_STATUS_FAIL_MS);
  #else
    bootInfo("servo_driver", true);
    bootUiStep("SERVO", "DIRECT PINS", BOOT_STATUS_OK_MS);
  #endif

    // Compile-time features (to give a bit of "liveliness")
    String feat = String("") + (IR_ENABLED?"IR ":"") + (RFID_ENABLED?"RFID ":"") + (ULTRA_ENABLED?"ULTRA ":"") + (LASER_ENABLED?"LASER ":"");
    if (feat.length() > 0) bootUiStep("FEAT", feat, BOOT_STATUS_STEP_MS);

    bootUiStep("READY", "", BOOT_STATUS_OK_MS);
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
  String line; if (Protocol::readLine(SERIAL_IO, line)) handleJson(line);
  robot.update();
#if OLED_ENABLED
  g_oled.update();
#endif
    // Peripherals polling
  #if RFID_ENABLED
    if (g_rfid.poll()){
      g_lastRfid = g_rfid.lastUid();
      String evt = String("{\"ok\":true,\"event\":\"rfid\",\"uid\":\"") + Protocol::escape(g_lastRfid) + "\"}";
      SERIAL_IO.println(evt);
  #if LCD_ENABLED
      // Show brief RFID on main status LCD (LCD1)
      String tail = g_lastRfid; if (tail.length()>8) tail = tail.substring(tail.length()-8);
      g_lcdStatus.showTo(LCD_TGT_1, "RFID", tail, true);

      // Normalize UID (remove non-alnum, uppercase)
      String norm = "";
      for (size_t _i = 0; _i < g_lastRfid.length(); ++_i){
        char c = g_lastRfid[_i];
        if ((c >= '0' && c <= '9') || (c >= 'A' && c <= 'F') || (c >= 'a' && c <= 'f')){
          if (c >= 'a' && c <= 'f') c = c - ('a' - 'A');
          norm += c;
        }
      }

      // Owner UID (uppercase, no separators)
      const String owner = String("F3A186A5");
            unsigned long now = millis();
            if (norm.equalsIgnoreCase(owner)){
              // update owner last seen (allow immediate re-reads)
              g_lastOwnerUid = norm;
              g_lastOwnerRfidMs = now;
        // Greet owner on LCD1
        g_lcdStatus.showTo(LCD_TGT_1, "Merhaba", "Sahip", true);
        playCuteSound(CUTE_SUPER_HAPPY, true);
        // Enqueue sequence: walle then three bb8 variants
        enqueueSong("walle");
        enqueueSong("bb8_1");
        enqueueSong("bb8_2");
        enqueueSong("bb8_3");
            }
  #endif
    }
  #endif
  #if ULTRA_ENABLED
    if (g_ultra.measureIfDue(ULTRA_MEASURE_INTERVAL_MS)){
      g_ultraCm = g_ultra.lastCm();
    }
    if (g_avoidEnable && robot.getMode()==MODE_SIT){
      if (!isnan(g_ultraCm) && g_ultraCm>0 && g_ultraCm < AVOID_DISTANCE_CM){
        robot.setDriveCmd(AVOID_REVERSE_SPEED);
  #if LCD_ENABLED
        g_lcdStatus.show("AVOID", String((int)g_ultraCm) + "cm");
  #endif
  // (removed) processSongQueue was here under ULTRA condition; moved to main BUZZER section
      }
    }
#if ULTRA_ENABLED && BUZZER_ENABLED
    // Parking-style proximity beeps while sitting in avoid-mode
    if (g_avoidEnable && robot.getMode()==MODE_SIT){
      if (!isnan(g_ultraCm) && g_ultraCm>0 && g_ultraCm < AVOID_DISTANCE_CM){
        unsigned long nowp = millis();
        if (g_ultraCm <= AVOID_CONTINUOUS_CM){
          // Very close: start a sustained/continuous tone until cleared (ms==0 => indefinite)
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
          // Parking beeps: interval scales with distance
          unsigned long interval = (unsigned long)constrain(g_ultraCm * 5.0f + 40.0f, 50.0f, 800.0f);
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
          // Ensure continuous flag cleared and any sustained tone is stopped
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
  String k;
  if (g_ir.poll(k)){
    g_irMenu.onKey(k, robot);
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
  g_ebyteRadio.poll();
  g_nema.update();
  // Telemetry periodic output
  if (telemetryOn && millis() - lastTelemetryMs >= telemetryInterval){
    lastTelemetryMs = millis(); robot.imu.read();
      String out = "{\"ok\":true,\"telemetry\":true,\"pitch\":"; out += robot.imu.getPitch();
      out += ",\"roll\":"; out += robot.imu.getRoll();
      out += ",\"pose\": ["; for (int i=0;i<SERVO_COUNT_TOTAL;i++){ if(i) out += ","; out += (int)robot.servos.get(i);} out += "],\"stepper_pos\": ["; out += robot.steppers.pos1(); out += ","; out += robot.steppers.pos2(); out += "]";
  #if RFID_ENABLED
      out += ",\"rfid\":\""; out += Protocol::escape(g_lastRfid); out += "\"";
  #endif
  #if ULTRA_ENABLED
      out += ",\"ultra_cm\":"; out += (isnan(g_ultraCm)?String("null"):String(g_ultraCm,1));
  #endif
      out += "}";
      SERIAL_IO.println(out);
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
