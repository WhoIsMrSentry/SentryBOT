#include <Arduino.h>
#include "xConfig.h"
#include "xProtocol.h"
#include "xRobot.h"
#include <EEPROM.h>
#include "xPeripherals.h"

#include "app/xLcdHub.h"
#include "app/xIrMenuController.h"
#include "app/xCommands.h"

Robot robot;
unsigned long lastHeartbeatMs = 0;
bool telemetryOn = false;
unsigned long telemetryInterval = 100;
unsigned long lastTelemetryMs = 0;

#if RFID_ENABLED
RfidReader g_rfid;
String g_lastRfid;
#endif
#if LCD_ENABLED
LcdDisplay g_lcd1;
#if LCD2_ENABLED
LcdDisplay g_lcd2;
#endif

bool g_lcd1Ok = false;
#if LCD2_ENABLED
bool g_lcd2Ok = false;
#endif
uint8_t g_lcdRouteMask = LCD_TGT_BOTH;
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
BuzzerOut g_buzzerDefaultOut = BUZZER_OUT_QUIET;
#endif
#if IR_ENABLED
IrKeyReader g_ir;
#endif

#if IR_ENABLED
IrMenuController g_irMenu;
#endif

void setup(){
  SERIAL_IO.begin(ROBOT_SERIAL_BAUD);
  robot.begin();
  // Auto-load IMU offsets if present
  if (EEPROM.read(EEPROM_ADDR_MAGIC)==EEPROM_MAGIC){ float p,r; EEPROM.get(EEPROM_ADDR_IMU_OFF,p); EEPROM.get(EEPROM_ADDR_IMU_OFF+sizeof(float),r); robot.imu.setOffsets(p,r); }
  Protocol::sendOk("ready");
#if LCD_ENABLED
  Wire.begin();
#if defined(ARDUINO_ARCH_AVR)
  Wire.setWireTimeout(25000, true);
#endif
  bool p1 = i2cDevicePresent(LCD_I2C_ADDR);
#if LCD2_ENABLED
  bool p2 = i2cDevicePresent(LCD2_I2C_ADDR);
#else
  bool p2 = false;
#endif

  g_lcd1Ok = p1;
#if LCD2_ENABLED
  g_lcd2Ok = p2;
#endif

  // Auto-promote: if only one LCD exists, prefer treating it as 16x2 (prevents 2x8 split look on 16x2 modules).
  bool onlyOne = (p1 && !p2) || (!p1 && p2);

  if (p1){
    uint8_t cols = LCD_COLS;
    uint8_t rows = LCD_ROWS;
    bool split = (bool)LCD_16X1_SPLIT_ROW;
    if (LCD_AUTO_PROMOTE_16X2_IF_SINGLE && onlyOne && cols == 16 && rows == 1){
      rows = 2;
      split = false;
    }
    g_lcd1.begin(LCD_I2C_ADDR, cols, rows, split);
  }

#if LCD2_ENABLED
  if (p2){
    uint8_t cols = LCD2_COLS;
    uint8_t rows = LCD2_ROWS;
    bool split = (bool)LCD2_16X1_SPLIT_ROW;
    if (LCD_AUTO_PROMOTE_16X2_IF_SINGLE && onlyOne && cols == 16 && rows == 1){
      rows = 2;
      split = false;
    }
    g_lcd2.begin(LCD2_I2C_ADDR, cols, rows, split);
  }
#endif

  // Default routing from config (still falls back to detected if requested target isn't present)
  if (LCD_ROUTE_DEFAULT == 2) g_lcdRouteMask = LCD_TGT_1;
  else if (LCD_ROUTE_DEFAULT == 3) g_lcdRouteMask = LCD_TGT_2;
  else if (LCD_ROUTE_DEFAULT == 1) g_lcdRouteMask = LCD_TGT_BOTH;
  else g_lcdRouteMask = LCD_TGT_BOTH;

  // Eğer iki ekran da yoksa firmware yine çalışır; sadece LCD çıktısı no-op olur.
  g_lcdStatus.begin("READY", 3000);

    if (BOOT_STATUS_ENABLED && lcdHubAny()){
    bootUiStep("SentryBOT", "BOOT", BOOT_SPLASH_MS);

    // LCDs
    bootInfo("lcd1", g_lcd1Ok);
    bootUiStep("LCD1", g_lcd1Ok ? "OK" : "MISSING", g_lcd1Ok ? BOOT_STATUS_OK_MS : BOOT_STATUS_FAIL_MS);

  #if LCD2_ENABLED
    bootInfo("lcd2", g_lcd2Ok);
    bootUiStep("LCD2", g_lcd2Ok ? "OK" : "MISSING", g_lcd2Ok ? BOOT_STATUS_OK_MS : BOOT_STATUS_FAIL_MS);
  #endif

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
#if BOOT_BEEP
  g_buzzer.beepOn(g_buzzerDefaultOut, 2200, 50);
#endif
#endif
#if IR_ENABLED
  g_ir.begin(IR_PIN);
#if LCD_ENABLED
  // IR menü olayları LCD'de 3sn gösterilir; UNKNOWN gürültüsü yazdırılmaz.
  g_irMenu.setLcdPrint([](const String &top, const String &bottom){ g_lcdStatus.show(top, bottom); });
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
    // Peripherals polling
  #if RFID_ENABLED
    if (g_rfid.poll()){
      g_lastRfid = g_rfid.lastUid();
      String evt = String("{\"ok\":true,\"event\":\"rfid\",\"uid\":\"") + Protocol::escape(g_lastRfid) + "\"}";
      SERIAL_IO.println(evt);
  #if LCD_ENABLED
      String tail = g_lastRfid; if (tail.length()>8) tail = tail.substring(tail.length()-8);
      g_lcdStatus.show("RFID", tail);
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
      }
    }
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
  g_song.update();
  g_buzzer.update();
#endif
  // Heartbeat timeout safety
  if (HEARTBEAT_TIMEOUT_MS>0 && (millis() - lastHeartbeatMs > HEARTBEAT_TIMEOUT_MS)){
    robot.estop();
  }
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
}
