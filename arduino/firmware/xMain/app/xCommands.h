#ifndef SENTRY_APP_COMMANDS_H
#define SENTRY_APP_COMMANDS_H

#include <Arduino.h>
#include "../xConfig.h"
#include "../xProtocol.h"
#include "../xRobot.h"
#include "xIrMenuController.h"
#include "xCuteBuzzer.h"

// Globals owned by xMain.ino
extern Robot robot;
extern unsigned long lastHeartbeatMs;
extern bool telemetryOn;
extern unsigned long telemetryInterval;
extern unsigned long lastTelemetryMs;

// Last brain speech text (set via NDJSON cmd)
extern String g_lastSpeech;

// Forward declarations for safety/calibration helpers owned by xMain.ino
void triggerSafetyEstop(const __FlashStringHelper *reason);
void clearSafetyEstop();
void startEncoderCalibration(unsigned long durMs, bool updateLcd);

#if VIRTUAL_MENU_ENABLED
// IR virtual menu instance (defined in xMain.ino)
extern IrMenuController g_irMenu;
#endif

#if RFID_ENABLED
#include "../xPeripherals.h"
extern RfidReader g_rfid;
extern String g_lastRfid;
#endif

#if HALL_ENCODER_ENABLED
#include "../peripherals/xHallEncoder.h"
extern HallEncoder g_hall0;
extern HallEncoder g_hall1;
#endif

#if LCD_ENABLED
#include "xLcdHub.h"
#endif

#if ULTRA_ENABLED
#include "../xPeripherals.h"
extern Ultrasonic g_ultra;
extern float g_ultraCm;
extern bool g_avoidEnable;
#endif

#if LASER_ENABLED
#include "../xPeripherals.h"
extern LaserPair g_lasers;
#endif

#if BUZZER_ENABLED
#include "../xPeripherals.h"
extern BuzzerPair g_buzzer;
extern BuzzerSongPlayer g_song;
extern BuzzerOut g_buzzerDefaultOut;
#endif

#if DS18_ENABLED
#include "../xPeripherals.h"
extern Ds18b20Manager g_ds18;
#endif

static inline bool isIrKeyStr(const String &k){
  if (k.length() == 1){
    char c = k[0];
    return (c >= '0' && c <= '9') || c == '*' || c == '#';
  }
  return k == "UP" || k == "DOWN" || k == "LEFT" || k == "RIGHT" || k == "OK";
}

// ── Idle liveliness (firmware-native breathing / micro-motion) ───────────
// Owned here; driven by livelinessTick() from the main loop. Keeps subtle
// head motion alive even if the Pi bridge briefly stalls.
bool                 g_livOn       = false;
static float         g_livAmp      = 4.0f;    // degrees
static float         g_livPanC     = 90.0f;   // pan center
static float         g_livTiltC    = 90.0f;   // tilt center
static unsigned long g_livPeriodMs = 4500;    // full cycle period
static bool          g_livMicro    = false;   // micro mode adds a faster pan flutter

static inline void livelinessTick(){
  if (!g_livOn || robot.isEstopped()) return;
  unsigned long period = g_livPeriodMs < 200 ? 200 : g_livPeriodMs;
  float phase = (float)(millis() % period) / (float)period;  // 0..1
  float s = sinf(phase * 6.2831853f);                        // breathing on tilt
  float tilt = g_livTiltC + g_livAmp * s;
  float pan = g_livPanC;
  if (g_livMicro){
    // faster, smaller pan flutter layered on top
    float s2 = sinf(phase * 6.2831853f * 3.0f);
    pan = g_livPanC + (g_livAmp * 0.5f) * s2;
  }
  robot.head(tilt, pan);  // robot.head expects (tilt, pan)
}

static inline void handleJson(const String &line){
  // Trim and check for bare IR key (no JSON structure)
  String trimmed = line;
  trimmed.trim();

  // If line doesn't start with { and looks like a bare shortcut/IR key
  if (trimmed.length() > 0 && trimmed[0] != '{'){
    if (trimmed.equalsIgnoreCase(F("cal"))){
      if (robot.isEstopped()){ Protocol::sendErr(F("estopped")); return; }
      robot.calibrateNeutral();
      Protocol::sendOk(F("calibrated"));
      return;
    }
    trimmed.toUpperCase();
    if (isIrKeyStr(trimmed)){
#if VIRTUAL_MENU_ENABLED
      g_irMenu.onKey(trimmed, robot);
      Protocol::sendOk(F("ir_key"));
#else
      Protocol::sendErr(F("menu_disabled"));
#endif
      return;
    }
  }

  // Extract optional correlation sequence id and echo it automatically in replies.
  bool hasSeq = false;
  long reqSeq = Protocol::parseJsonLongAfter(line, F("\"seq\":"), -1L, &hasSeq);
  Protocol::SeqScope _seqScope(hasSeq, reqSeq);

  // Handle ACKs for neopixel requests (from Pi): {"ok":true,"ack_seq":<num>}
  bool hasAckSeq = false;
  long sval = Protocol::parseJsonLongAfter(line, F("\"ack_seq\":"), 0L, &hasAckSeq);
  if (hasAckSeq && sval > 0){
    markNeopixelAck((uint16_t)sval);
  }

  String cmd = Protocol::parseJsonStringAfter(line, F("\"cmd\":"));
  if (cmd.length() == 0){
    if (hasAckSeq){
      if (hasSeq) Protocol::sendOk(F("ack"));
      return;
    }
    Protocol::sendErr(F("missing_cmd"));
    return;
  }

  if (cmd == F("hello")){
    SERIAL_IO.print(F("{\"ok\":true,\"msg\":\"hello\",\"fw\":\"xMain\",\"fw_ver\":\"2026.03\",\"servo_count\":"));
    SERIAL_IO.print((int)SERVO_COUNT_TOTAL);
    SERIAL_IO.print(F(",\"estop\":"));
    SERIAL_IO.print(robot.isEstopped() ? F("true") : F("false"));
    SERIAL_IO.print(F(",\"features\":[\"set_servo_index_deg\",\"set_pose\",\"stepper\",\"pid_enable\",\"pid_set\",\"track\",\"telemetry\",\"rfid\",\"ultra\",\"laser\",\"buzzer\",\"cute\",\"estop_clear\"]"));
    Protocol::endJsonReply(SERIAL_IO);
    return;
  }

  if (cmd == F("hb")){
    lastHeartbeatMs = millis();
    Protocol::sendOk(F("hb"));
    return;
  }

  if (cmd == F("estop")){
    triggerSafetyEstop(F("cmd"));
#if BUZZER_ENABLED
    g_buzzer.beepOn(BUZZER_OUT_LOUD, g_buzzerFreqLoud, 150);
#endif
    Protocol::sendOk(F("estopped"));
    return;
  }

  if (cmd == F("estop_clear")){
    clearSafetyEstop();
    Protocol::sendOk(F("estop_cleared"));
    return;
  }

  if (cmd == F("ir_key")){
#if VIRTUAL_MENU_ENABLED
    String key = Protocol::parseJsonStringAfter(line, F("\"key\":"));
    key.trim();
    key.toUpperCase();
    if (isIrKeyStr(key)){
      g_irMenu.onKey(key, robot);
      Protocol::sendOk(F("ir_key"));
    } else {
      Protocol::sendErr(F("bad_key"));
    }
#else
    Protocol::sendErr(F("menu_disabled"));
#endif
    return;
  }

  if (cmd == F("menu_goto")){
#if VIRTUAL_MENU_ENABLED
    String menu = Protocol::parseJsonStringAfter(line, F("\"menu\":"));
    if (menu.length() == 0) menu = Protocol::parseJsonStringAfter(line, F("\"target\":"));
    menu.trim();
    menu.toLowerCase();

    if (menu == F("home"))      { g_irMenu.gotoHome(); Protocol::sendOk(F("menu_home")); return; }
    if (menu == F("servo"))     { g_irMenu.gotoMenu(IrMenuController::MENU_SERVO,     robot); Protocol::sendOk(F("menu_servo"));     return; }
    if (menu == F("laser"))     { g_irMenu.gotoMenu(IrMenuController::MENU_LASER,     robot); Protocol::sendOk(F("menu_laser"));     return; }
    if (menu == F("ultra"))     { g_irMenu.gotoMenu(IrMenuController::MENU_ULTRA,     robot); Protocol::sendOk(F("menu_ultra"));     return; }
    if (menu == F("imu"))       { g_irMenu.gotoMenu(IrMenuController::MENU_IMU,       robot); Protocol::sendOk(F("menu_imu"));       return; }
    if (menu == F("rfid"))      { g_irMenu.gotoMenu(IrMenuController::MENU_RFID,      robot); Protocol::sendOk(F("menu_rfid"));      return; }
    if (menu == F("sound"))     { g_irMenu.gotoMenu(IrMenuController::MENU_SOUND,     robot); Protocol::sendOk(F("menu_sound"));     return; }
    if (menu == F("calibrate")) { g_irMenu.gotoMenu(IrMenuController::MENU_CALIBRATE, robot); Protocol::sendOk(F("menu_calibrate")); return; }
    if (menu == F("system"))    { g_irMenu.gotoMenu(IrMenuController::MENU_SYSTEM,    robot); Protocol::sendOk(F("menu_system"));    return; }
    if (menu == F("temps"))     { g_irMenu.gotoMenu(IrMenuController::MENU_TEMPS,     robot); Protocol::sendOk(F("menu_temps"));     return; }
    if (menu == F("alerts"))    { g_irMenu.gotoMenu(IrMenuController::MENU_ALERTS,    robot); Protocol::sendOk(F("menu_alerts"));    return; }
    if (menu == F("stats"))     { g_irMenu.gotoMenu(IrMenuController::MENU_STATS,     robot); Protocol::sendOk(F("menu_stats"));     return; }

    Protocol::sendErr(F("bad_menu"));
#else
    Protocol::sendErr(F("menu_disabled"));
#endif
    return;
  }

  if (cmd == F("lcd")){
#if LCD_ENABLED
    uint8_t tgt = lcdTargetMaskFromLine(line);
    String top = Protocol::parseJsonStringAfter(line, F("\"top\":"));
    String bottom = Protocol::parseJsonStringAfter(line, F("\"bottom\":"));
    if (top.length() == 0){
      top = Protocol::parseJsonStringAfter(line, F("\"msg\":"));
    }
    if (top.length() > 0){
      g_lcdStatus.showTo(tgt, top, bottom, true);
      Protocol::sendOk(F("lcd_ok"));
    } else {
      Protocol::sendErr(F("no_msg"));
    }
#else
    Protocol::sendErr(F("lcd_disabled"));
#endif
    return;
  }

  if (cmd == F("rfid_last")){
#if RFID_ENABLED
    SERIAL_IO.print(F("{\"ok\":true,\"rfid\":\""));
    Protocol::printEscaped(SERIAL_IO, g_lastRfid);
    SERIAL_IO.print('"');
    Protocol::endJsonReply(SERIAL_IO);
#else
    Protocol::sendErr(F("rfid_disabled"));
#endif
    return;
  }

  if (cmd == F("ultra_read")){
#if ULTRA_ENABLED
    SERIAL_IO.print(F("{\"ok\":true,\"cm\":"));
    if (isnan(g_ultraCm)) SERIAL_IO.print(F("null"));
    else SERIAL_IO.print(g_ultraCm, 1);
    Protocol::endJsonReply(SERIAL_IO);
#else
    Protocol::sendErr(F("ultra_disabled"));
#endif
    return;
  }

  if (cmd == F("temp_read")){
#if DS18_ENABLED
    g_ds18.forceRead();
    SERIAL_IO.print(F("{\"ok\":true,\"temps\":["));
    for (int i=0; i<DS18_SENSOR_COUNT; i++){
      if (i > 0) SERIAL_IO.print(',');
      float t = g_ds18.tempC(i);
      if (isnan(t)) SERIAL_IO.print(F("null"));
      else SERIAL_IO.print(t, 1);
    }
    SERIAL_IO.print(']');
    Protocol::endJsonReply(SERIAL_IO);
#else
    Protocol::sendErr(F("ds18_disabled"));
#endif
    return;
  }

  if (cmd == F("avoid")){
#if ULTRA_ENABLED
    g_avoidEnable = Protocol::parseJsonBoolAfter(line, F("\"enable\":"), false);
    Protocol::sendOk(g_avoidEnable ? F("avoid_on") : F("avoid_off"));
#else
    Protocol::sendErr(F("ultra_disabled"));
#endif
    return;
  }

  if (cmd == F("laser")){
#if LASER_ENABLED
    if (robot.isEstopped() && Protocol::parseJsonBoolAfter(line, F("\"on\":"), false)){
      Protocol::sendErr(F("estopped"));
      return;
    }
    bool both = Protocol::parseJsonBoolAfter(line, F("\"both\":"), false);
    int id = (int)Protocol::parseJsonLongAfter(line, F("\"id\":"), 0L);
    if (Protocol::parseJsonBoolAfter(line, F("\"on\":"), false)){
      if (both){ g_lasers.bothOn(); Protocol::sendOk(F("laser_both_on")); }
      else if (id==1 || id==2){ g_lasers.oneOn((uint8_t)id); Protocol::sendOk(F("laser_on")); }
      else { Protocol::sendErr(F("bad_id")); }
    } else {
      g_lasers.off();
      Protocol::sendOk(F("laser_off"));
    }
#else
    Protocol::sendErr(F("laser_disabled"));
#endif
    return;
  }

  if (cmd == F("sound")){
#if BUZZER_ENABLED
    String outMode = Protocol::parseJsonStringAfter(line, F("\"out\":"));
    if (outMode.length() == 0) outMode = Protocol::parseJsonStringAfter(line, F("\"mode\":"));
    if (outMode == F("loud")){
      g_buzzerDefaultOut = BUZZER_OUT_LOUD;
      g_song.setDefaultOut(g_buzzerDefaultOut);
      cuteBuzzerInit();
      Protocol::sendOk(F("sound_out_loud"));
      return;
    }
    if (outMode == F("quiet")){
      g_buzzerDefaultOut = BUZZER_OUT_QUIET;
      g_song.setDefaultOut(g_buzzerDefaultOut);
      cuteBuzzerInit();
      Protocol::sendOk(F("sound_out_quiet"));
      return;
    }
    bool hasBoth = false;
    bool bothEn = Protocol::parseJsonBoolAfter(line, F("\"both\":"), false, &hasBoth);
    if (hasBoth){
      g_buzzerBothEnabled = bothEn;
      Protocol::sendOk(bothEn ? F("sound_both_on") : F("sound_both_off"));
      return;
    }
    Protocol::sendErr(F("bad_out"));
#else
    Protocol::sendErr(F("buzzer_disabled"));
#endif
    return;
  }

  if (cmd == F("buzzer")){
#if BUZZER_ENABLED
    int freq = (int)constrain(Protocol::parseJsonLongAfter(line, F("\"freq\":"), 2200L), 200L, 4000L);
    int ms   = (int)constrain(Protocol::parseJsonLongAfter(line, F("\"ms\":"), 60L), 1L, 60000L);

    BuzzerOut out = g_buzzerDefaultOut;
    String outName = Protocol::parseJsonStringAfter(line, F("\"out\":"));
    if (outName == F("loud")) out = BUZZER_OUT_LOUD;
    else if (outName == F("quiet")) out = BUZZER_OUT_QUIET;

    g_buzzer.beepOn(out, (uint16_t)freq, (uint16_t)ms);
    Protocol::sendOk(F("beep"));
#else
    Protocol::sendErr(F("buzzer_disabled"));
#endif
    return;
  }

  if (cmd == F("sound_play")){
#if BUZZER_ENABLED
    String name = Protocol::parseJsonStringAfter(line, F("\"name\":"));
    BuzzerOut out = g_buzzerDefaultOut;
    String outName = Protocol::parseJsonStringAfter(line, F("\"out\":"));
    if (outName == F("loud")) out = BUZZER_OUT_LOUD;
    else if (outName == F("quiet")) out = BUZZER_OUT_QUIET;

    if (name.length()==0){ Protocol::sendErr(F("no_name")); return; }
    // Prevent overlap with any continuous warning tone before melody starts.
    g_buzzer.stop();
    g_song.play(name, out);
    Protocol::sendOk(F("sound_play"));
#else
    Protocol::sendErr(F("buzzer_disabled"));
#endif
    return;
  }

  if (cmd == F("speech")){
    String txt = Protocol::parseJsonStringAfter(line, F("\"text\":"));
    if (txt.length()==0){ Protocol::sendErr(F("no_text")); }
    else { g_lastSpeech = txt; Protocol::sendOk(F("speech_ok")); }
    return;
  }

  if (cmd == F("speech_play")){
#if VIRTUAL_MENU_ENABLED
    if (g_lastSpeech.length()==0){ Protocol::sendErr(F("no_speech")); return; }
    String pat = g_irMenu.textToMorse(g_lastSpeech);
    if (pat.length()==0){ Protocol::sendErr(F("bad_text")); return; }
    g_irMenu.startMorse(pat);
    Protocol::sendOk(F("speech_playing"));
#else
    Protocol::sendErr(F("menu_disabled"));
#endif
    return;
  }

  if (cmd == F("cute")){
#if BUZZER_ENABLED
    String name = Protocol::parseJsonStringAfter(line, F("\"name\":"));
    if (name.length()==0){ Protocol::sendErr(F("no_name")); return; }
    bool ok = playCuteSoundByName(name, true);
    if (ok) Protocol::sendOk(F("cute_played"));
    else Protocol::sendErr(F("unknown_cute_name"));
#else
    Protocol::sendErr(F("buzzer_disabled"));
#endif
    return;
  }

  if (cmd == F("set_servo")){
    if (robot.isEstopped()){ Protocol::sendErr(F("estopped")); return; }
    bool hasIdx = false;
    int idx = (int)Protocol::parseJsonLongAfter(line, F("\"index\":"), -1L, &hasIdx);
    float deg = Protocol::parseJsonFloatAfter(line, F("\"deg\":"), 90.0f);
    if (hasIdx && idx>=0 && idx<SERVO_COUNT_TOTAL){ robot.writeServoLimited(idx,deg); Protocol::sendOk(); }
    else Protocol::sendErr(F("bad_index"));
    return;
  }

  if (cmd == F("set_pose")){
    if (robot.isEstopped()){ Protocol::sendErr(F("estopped")); return; }
    int pk = Protocol::findKey(line, F("\"pose\":"));
    int lb = (pk >= 0) ? line.indexOf('[', pk) : line.indexOf('[');
    int rb = (lb >= 0) ? line.indexOf(']', lb + 1) : -1;
    if (lb > 0 && rb > lb){
      uint8_t pose[SERVO_COUNT_TOTAL];
      int i=0;
      String nums=line.substring(lb+1,rb);
      nums += ',';
      int s=0;
      for (int k=0;k<nums.length() && i<SERVO_COUNT_TOTAL;k++) if(nums[k]==','){
        pose[i++] = (uint8_t) constrain(nums.substring(s,k).toInt(),0,180);
        s=k+1;
      }
      long durMs = Protocol::parseJsonLongAfter(line, F("\"duration_ms\":"), 0L);
      if (i==SERVO_COUNT_TOTAL){
        if (durMs>0){
          // Use temporary easing speed so global speed is automatically restored once settled.
          float maxDelta = 0.0f;
          for (int j=0;j<SERVO_COUNT_TOTAL;j++){
            float d = fabs((float)pose[j] - robot.servos.get(j));
            if (d>maxDelta) maxDelta=d;
          }
          if (maxDelta>0){
            float speed = (maxDelta / ((float)durMs / 1000.0f));
            robot.servos.setTemporarySpeed(speed);
          }
        }
        robot.writePoseLimited(pose);
        Protocol::sendOk();
        return;
      }
    }
    Protocol::sendErr(F("bad_pose"));
    return;
  }

  if (cmd == F("stepper")){
    if (robot.isEstopped()){ Protocol::sendErr(F("estopped")); return; }
    bool vel = (Protocol::parseJsonStringAfter(line, F("\"mode\":")) == F("vel"));
    int id = (int)constrain(Protocol::parseJsonLongAfter(line, F("\"id\":"), 0L), 0L, 1L);
    long val = Protocol::parseJsonLongAfter(line, F("\"value\":"), 0L);
    if (vel){ robot.steppers.setSpeedOne(id, (float)val); }
    else { robot.steppers.moveToOne(id, val); }
    bool hasDrive = false;
    long d = Protocol::parseJsonLongAfter(line, F("\"drive\":"), 0L, &hasDrive);
    if (hasDrive){ robot.setDriveCmd((float)d); }
    Protocol::sendOk();
    return;
  }

  if (cmd == F("home")){
    if (robot.isEstopped()){ Protocol::sendErr(F("estopped")); return; }
    StepperPair::HomeResult hr = robot.steppers.homeBoth();
    if (hr == StepperPair::HOME_OK) Protocol::sendOk(F("homed"));
    else if (hr == StepperPair::HOME_NO_LIMITS) Protocol::sendErr(F("no_limit_switches"));
    else Protocol::sendErr(F("home_timeout"));
    return;
  }
  if (cmd == F("zero_now")){ robot.steppers.zeroNow(); Protocol::sendOk(F("zeroed_now")); return; }

  if (cmd == F("zero_set")){
    long p1 = Protocol::parseJsonLongAfter(line, F("\"p1\":"), 0L);
    long p2 = Protocol::parseJsonLongAfter(line, F("\"p2\":"), 0L);
    robot.steppers.zeroSet(p1,p2);
    Protocol::sendOk(F("zero_set"));
    return;
  }

  if (cmd == F("stepper_cfg")){
    bool hasMax = false, hasAcc = false;
    float v = Protocol::parseJsonFloatAfter(line, F("\"maxSpeed\":"), 0.0f, &hasMax);
    float a = Protocol::parseJsonFloatAfter(line, F("\"accel\":"), 0.0f, &hasAcc);
    if (hasMax) robot.steppers.setMaxSpeed(v);
    if (hasAcc) robot.steppers.setAcceleration(a);
    Protocol::sendOk(F("stepper_cfg"));
    return;
  }

  // PID commands for closed-loop stepper control
  if (cmd == F("pid_enable")){
    int id = (int)constrain(Protocol::parseJsonLongAfter(line, F("\"id\":"), 0L), 0L, 1L);
    bool en = Protocol::parseJsonBoolAfter(line, F("\"enable\":"), false);
    robot.steppers.enablePid(id, en);
    Protocol::sendOk(en ? F("pid_enabled") : F("pid_disabled"));
    return;
  }

  if (cmd == F("pid_set")){
    int id = (int)constrain(Protocol::parseJsonLongAfter(line, F("\"id\":"), 0L), 0L, 1L);
    float curKp=0, curKi=0, curKd=0;
    robot.steppers.getPidGains(id, curKp, curKi, curKd);
    bool hasKp=false, hasKi=false, hasKd=false, hasTgt=false;
    float nKp = Protocol::parseJsonFloatAfter(line, F("\"kp\":"), curKp, &hasKp);
    float nKi = Protocol::parseJsonFloatAfter(line, F("\"ki\":"), curKi, &hasKi);
    float nKd = Protocol::parseJsonFloatAfter(line, F("\"kd\":"), curKd, &hasKd);
    if (hasKp || hasKi || hasKd){
      robot.steppers.configurePid(id, hasKp?nKp:curKp, hasKi?nKi:curKi, hasKd?nKd:curKd);
    }
    float t = Protocol::parseJsonFloatAfter(line, F("\"target\":"), 0.0f, &hasTgt);
    if (hasTgt){ robot.steppers.setTargetSpeed(id, t); }
    Protocol::sendOk(F("pid_set"));
    return;
  }

  if (cmd == F("pid_status")){
    int id = (int)constrain(Protocol::parseJsonLongAfter(line, F("\"id\":"), 0L), 0L, 1L);
    float measured = robot.steppers.getMeasuredSpeed(id);
    float target = robot.steppers.getPidTarget(id);
    bool stalled = robot.steppers.isStalled(id);
    SERIAL_IO.print(F("{\"ok\":true,\"id\":"));
    SERIAL_IO.print(id);
    SERIAL_IO.print(F(",\"measured\":"));
    SERIAL_IO.print(measured, 1);
    SERIAL_IO.print(F(",\"target\":"));
    SERIAL_IO.print(target, 1);
    SERIAL_IO.print(F(",\"stalled\":"));
    SERIAL_IO.print(stalled ? F("true") : F("false"));
    Protocol::endJsonReply(SERIAL_IO);
    return;
  }

  if (cmd == F("pid_save")){
    int id = (int)constrain(Protocol::parseJsonLongAfter(line, F("\"id\":"), 0L), 0L, 1L);
    robot.steppers.savePidToEeprom(id);
    Protocol::sendOk(F("pid_saved"));
    return;
  }

  if (cmd == F("pid_load")){
    int id = (int)constrain(Protocol::parseJsonLongAfter(line, F("\"id\":"), 0L), 0L, 1L);
    bool ok = robot.steppers.loadPidFromEeprom(id);
    if (ok) Protocol::sendOk(F("pid_loaded")); else Protocol::sendErr(F("pid_not_saved"));
    return;
  }

  if (cmd == F("pid_clear_stall")){
    int id = (int)constrain(Protocol::parseJsonLongAfter(line, F("\"id\":"), 0L), 0L, 1L);
    robot.steppers.clearStall(id);
    Protocol::sendOk(F("stall_cleared"));
    return;
  }

  if (cmd == F("pid_reset")){
    int id = (int)constrain(Protocol::parseJsonLongAfter(line, F("\"id\":"), 0L), 0L, 1L);
    robot.steppers.resetPidIntegrator(id);
    Protocol::sendOk(F("pid_reset"));
    return;
  }

  if (cmd == F("calibrate") || cmd == F("cal")){
    if (robot.isEstopped()){ Protocol::sendErr(F("estopped")); return; }
    robot.calibrateNeutral();
    Protocol::sendOk(F("calibrated"));
    return;
  }
  if (cmd == F("stand")){ robot.setModeStand(); Protocol::sendOk(F("stand")); return; }
  if (cmd == F("sit")){ robot.setModeSit(); Protocol::sendOk(F("sit")); return; }

  if (cmd == F("imu_read")){
    robot.imu.read();
    SERIAL_IO.print(F("{\"ok\":true,\"pitch\":"));
    SERIAL_IO.print(robot.imu.getPitch(), 2);
    SERIAL_IO.print(F(",\"roll\":"));
    SERIAL_IO.print(robot.imu.getRoll(), 2);
    SERIAL_IO.print(F(",\"msg\":\"pitch="));
    SERIAL_IO.print(robot.imu.getPitch(), 2);
    SERIAL_IO.print(F(",roll="));
    SERIAL_IO.print(robot.imu.getRoll(), 2);
    SERIAL_IO.print('"');
    Protocol::endJsonReply(SERIAL_IO);
    return;
  }

  if (cmd == F("imu_cal")){ robot.imu.calibrateLevel(); Protocol::sendOk(F("imu_calibrated")); return; }

  if (cmd == F("drive")){
    if (robot.isEstopped()){ Protocol::sendErr(F("estopped")); return; }
    long v = Protocol::parseJsonLongAfter(line, F("\"value\":"), 0L);
    robot.setDriveCmd((float)v);
    Protocol::sendOk(F("drive_set"));
    return;
  }

  if (cmd == F("eeprom_save")){
    float p,r;
    robot.imu.getOffsets(p,r);
    EEPROM.update(EEPROM_ADDR_MAGIC, EEPROM_MAGIC);
    EEPROM.put(EEPROM_ADDR_IMU_OFF, p);
    EEPROM.put(EEPROM_ADDR_IMU_OFF+sizeof(float), r);
    Protocol::sendOk(F("saved"));
    return;
  }

  if (cmd == F("eeprom_load")){
    if (EEPROM.read(EEPROM_ADDR_MAGIC)==EEPROM_MAGIC){
      float p,r;
      EEPROM.get(EEPROM_ADDR_IMU_OFF,p);
      EEPROM.get(EEPROM_ADDR_IMU_OFF+sizeof(float),r);
      robot.imu.setOffsets(p,r);
      Protocol::sendOk(F("loaded"));
    } else {
      Protocol::sendErr(F("no_data"));
    }
    return;
  }

  if (cmd == F("encoder_calibrate")){
#if HALL_ENCODER_ENABLED
    unsigned long dur = (unsigned long)constrain(Protocol::parseJsonLongAfter(line, F("\"duration_ms\":"), 5000L), 500L, 30000L);
    startEncoderCalibration(dur, false);
    Protocol::sendOk(F("encoder_calibrating"));
#else
    Protocol::sendErr(F("halls_disabled"));
#endif
    return;
  }

  if (cmd == F("policy")){
    if (robot.isEstopped()){ Protocol::sendErr(F("estopped")); return; }
    int pk = Protocol::findKey(line, F("\"pose\":"));
    if (pk >= 0){
      int lb = line.indexOf('[', pk);
      int rb = (lb >= 0) ? line.indexOf(']', lb + 1) : -1;
      if (lb > 0 && rb > lb){
        uint8_t pose[SERVO_COUNT_TOTAL];
        int i=0;
        String nums=line.substring(lb+1,rb);
        nums += ',';
        int s=0;
        for(int k=0;k<nums.length() && i<SERVO_COUNT_TOTAL;k++) if(nums[k]==','){
          pose[i++] = (uint8_t)constrain(nums.substring(s,k).toInt(),0,180);
          s=k+1;
        }
        if (i==SERVO_COUNT_TOTAL) robot.servos.writePose(pose);
      }
    }

    int sk = Protocol::findKey(line, F("\"steppers\":"));
    if (sk >= 0){
      int ls = line.indexOf('[', sk);
      int rs = (ls >= 0) ? line.indexOf(']', ls + 1) : -1;
      if (ls > 0 && rs > ls){
        String nums=line.substring(ls+1,rs);
        nums += ',';
        long v[2]={0,0};
        int i=0;
        int s=0;
        for(int k=0;k<nums.length() && i<2;k++) if(nums[k]==','){
          v[i++] = nums.substring(s,k).toInt();
          s=k+1;
        }
        if (i>=1) robot.steppers.setSpeedOne(0, (float)v[0]);
        if (i>=2) robot.steppers.setSpeedOne(1, (float)v[1]);
      }
    }

    Protocol::sendOk(F("policy_applied"));
    return;
  }

  if (cmd == F("track")){
    if (robot.isEstopped()){ Protocol::sendErr(F("estopped")); return; }
    float tilt = robot.servos.getTarget(1);
    float pan  = robot.servos.getTarget(0);
    bool hasT = false, hasP = false, hasD = false;

    float tVal = Protocol::parseJsonFloatAfter(line, F("\"head_tilt\":"), tilt, &hasT);
    if (!hasT) tVal = Protocol::parseJsonFloatAfter(line, F("\"tilt\":"), tilt, &hasT);
    if (hasT) tilt = tVal;

    float pVal = Protocol::parseJsonFloatAfter(line, F("\"head_pan\":"), pan, &hasP);
    if (!hasP) pVal = Protocol::parseJsonFloatAfter(line, F("\"pan\":"), pan, &hasP);
    if (hasP) pan = pVal;

    long drive = Protocol::parseJsonLongAfter(line, F("\"drive\":"), 0L, &hasD);
    if (hasT || hasP) robot.head(tilt, pan);
    if (hasD) robot.setDriveCmd((float)drive);
    Protocol::sendOk(F("track_ack"));
    return;
  }

  if (cmd == F("get_state")){
    robot.imu.read();
    SERIAL_IO.print(F("{\"ok\":true,\"mode\":"));
    SERIAL_IO.print(robot.getMode()==MODE_HEAD_TRACK ? F("\"stand\"") : F("\"sit\""));
    SERIAL_IO.print(F(",\"estop\":"));
    SERIAL_IO.print(robot.isEstopped() ? F("true") : F("false"));
    SERIAL_IO.print(F(",\"i2c_errors\":"));
    SERIAL_IO.print((unsigned long)Protocol::getI2cErrorCount());
    SERIAL_IO.print(F(",\"pitch\":"));
    SERIAL_IO.print(robot.imu.getPitch(), 2);
    SERIAL_IO.print(F(",\"roll\":"));
    SERIAL_IO.print(robot.imu.getRoll(), 2);
    SERIAL_IO.print(F(",\"pose\":["));
    for (int i=0;i<SERVO_COUNT_TOTAL;i++){
      if(i) SERIAL_IO.print(',');
      SERIAL_IO.print((int)robot.servos.get(i));
    }
    SERIAL_IO.print(F("],\"stepper_pos\":["));
    SERIAL_IO.print(robot.steppers.pos1());
    SERIAL_IO.print(',');
    SERIAL_IO.print(robot.steppers.pos2());
    SERIAL_IO.print(']');
    Protocol::endJsonReply(SERIAL_IO);
    return;
  }

  if (cmd == F("telemetry_start")){
    bool hasInt = false;
    long v = Protocol::parseJsonLongAfter(line, F("\"interval_ms\":"), (long)telemetryInterval, &hasInt);
    if (hasInt && v > 0){
      telemetryInterval = max((unsigned long)TELEMETRY_MIN_INTERVAL_MS, (unsigned long)v);
    }
    telemetryOn = true;
    lastTelemetryMs = millis();
    Protocol::sendOk(F("telemetry_on"));
    return;
  }

  if (cmd == F("telemetry_stop")){ telemetryOn=false; Protocol::sendOk(F("telemetry_off")); return; }

  if (cmd == F("tune")){
    bool hasServoSpd = false;
    float sSpd = Protocol::parseJsonFloatAfter(line, F("\"servo_speed\":"), 0.0f, &hasServoSpd);
    if (hasServoSpd && sSpd > 0.0f) robot.setServoSpeed(sSpd);

    int pStart = -1, pEnd = -1;
    if (Protocol::findObjectBounds(line, F("\"pid\":"), pStart, pEnd)){
      float kp = 0, ki = 0, kd = 0;
      robot.steppers.getPidGains(0, kp, ki, kd);
      kp = Protocol::parseJsonFloatAfter(line, F("\"kp\":"), kp, nullptr, pStart, pEnd);
      ki = Protocol::parseJsonFloatAfter(line, F("\"ki\":"), ki, nullptr, pStart, pEnd);
      kd = Protocol::parseJsonFloatAfter(line, F("\"kd\":"), kd, nullptr, pStart, pEnd);
      robot.steppers.configurePid(0, kp, ki, kd);
      robot.steppers.configurePid(1, kp, ki, kd);
    }

    int sStart = -1, sEnd = -1;
    if (Protocol::findObjectBounds(line, F("\"skate\":"), sStart, sEnd)){
      float skp = 0, ski = 0, skd = 0;
      robot.getSkateGains(skp, ski, skd);
      float smax = robot.getSkateSpeedLimit();
      skp  = Protocol::parseJsonFloatAfter(line, F("\"kp\":"),  skp,  nullptr, sStart, sEnd);
      ski  = Protocol::parseJsonFloatAfter(line, F("\"ki\":"),  ski,  nullptr, sStart, sEnd);
      skd  = Protocol::parseJsonFloatAfter(line, F("\"kd\":"),  skd,  nullptr, sStart, sEnd);
      smax = Protocol::parseJsonFloatAfter(line, F("\"max\":"), smax, nullptr, sStart, sEnd);
      robot.setSkateGains(skp, ski, skd);
      robot.setSkateSpeedLimit(smax);
    }

    Protocol::sendOk(F("tuned"));
    return;
  }

  if (cmd == F("liveliness")){
    bool enable = Protocol::parseJsonBoolAfter(line, F("\"enable\":"), false);
    if (!enable){
      g_livOn = false;
      if (!robot.isEstopped()) robot.head(g_livTiltC, g_livPanC);
      Protocol::sendOk(F("liveliness_off"));
      return;
    }
    if (robot.isEstopped()){ Protocol::sendErr(F("estopped")); return; }
    bool hasAmp=false, hasPer=false, hasPan=false, hasTilt=false;
    float amp = Protocol::parseJsonFloatAfter(line, F("\"amplitude_deg\":"), g_livAmp, &hasAmp);
    long per = Protocol::parseJsonLongAfter(line, F("\"period_ms\":"), (long)g_livPeriodMs, &hasPer);
    float panC = Protocol::parseJsonFloatAfter(line, F("\"pan_center\":"), g_livPanC, &hasPan);
    float tiltC = Protocol::parseJsonFloatAfter(line, F("\"tilt_center\":"), g_livTiltC, &hasTilt);
    if (hasAmp)  g_livAmp = amp;
    if (hasPer && per > 0) g_livPeriodMs = (unsigned long)per;
    if (hasPan)  g_livPanC = panC;
    if (hasTilt) g_livTiltC = tiltC;
    g_livMicro = (Protocol::parseJsonStringAfter(line, F("\"mode\":")) == F("micro"));
    g_livOn = true;
    Protocol::sendOk(F("liveliness_on"));
    return;
  }

  Protocol::sendErr(F("unknown_cmd"));
}

#endif // SENTRY_APP_COMMANDS_H
