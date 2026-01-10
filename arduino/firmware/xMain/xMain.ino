#include <Arduino.h>
#include "xConfig.h"
#include "xProtocol.h"
#include "xRobot.h"
#include <EEPROM.h>
#include "xPeripherals.h"

Robot robot;
static unsigned long lastHeartbeatMs = 0;
static bool telemetryOn = false; static unsigned long telemetryInterval = 100; static unsigned long lastTelemetryMs = 0;

#if RFID_ENABLED
static RfidReader g_rfid;
static String g_lastRfid;
#endif
#if LCD_ENABLED
static LcdDisplay g_lcd;
#endif
#if ULTRA_ENABLED
static Ultrasonic g_ultra; static float g_ultraCm = NAN; static bool g_avoidEnable = AVOID_ENABLE_DEFAULT;
#endif
#if LASER_ENABLED
static LaserPair g_lasers;
#endif
#if BUZZER_ENABLED
static BuzzerPair g_buzzer;
static BuzzerSongPlayer g_song;
static BuzzerOut g_buzzerDefaultOut = BUZZER_OUT_QUIET;
#endif
#if IR_ENABLED
static IrKeyReader g_ir;
#endif

#if IR_ENABLED
// IR command state machine: tokens are entered as "*<digits>" and committed either by
// - waiting IR_TOKEN_TIMEOUT_MS with no new digits, or
// - pressing '*' again, or
// - pressing 'OK' / '#'
// Example flow: *1 (menu=1 servo), *4 (servo=4), *90 (angle=90)
class IrMenuController {
public:
  void reset(){ _menu = 0; _servoSel = -1; _token = ""; _capture=false; _lastDigitMs=0; }

  void onKey(const String &k, Robot &robot){
    if (k == "UNKNOWN") return;

    // Direct controls (no menu needed)
    if (!_capture && _menu==0){
      if (k == "UP"){ robot.setModeStand(); emitEvent("stand"); return; }
      if (k == "DOWN"){ robot.setModeSit(); emitEvent("sit"); return; }
      if (k == "LEFT"){ robot.setDriveCmd(-200); emitEvent("drive", -200); return; }
      if (k == "RIGHT"){ robot.setDriveCmd(200); emitEvent("drive", 200); return; }
      if (k == "OK"){ robot.setDriveCmd(0); emitEvent("drive", 0); return; }
    }

    if (k == "*"){
      // Commit previous token (if any) then start capturing a new one
      commitTokenIfAny(robot);
      _capture = true;
      _token = "";
      _lastDigitMs = 0;
      emitEvent("token_start");
      return;
    }

    if (k == "OK" || k == "#"){
      commitTokenIfAny(robot);
      _capture = false;
      _token = "";
      return;
    }

    if (isDigitKey(k)){
      if (!_capture) return;
      _token += k;
      _lastDigitMs = millis();
      return;
    }
  }

  void tick(Robot &robot){
    if (!_capture) return;
    if (_token.length()==0) return;
    if (_lastDigitMs==0) return;
    if (millis() - _lastDigitMs >= (unsigned long)IR_TOKEN_TIMEOUT_MS){
      commitTokenIfAny(robot);
      _capture = false;
      _token = "";
    }
  }

private:
  static bool isDigitKey(const String &k){ return k.length()==1 && k[0]>='0' && k[0]<='9'; }

  void commitTokenIfAny(Robot &robot){
    if (_token.length()==0) return;
    long v = _token.toInt();
    applyToken(v, robot);
    _token = "";
    _lastDigitMs = 0;
  }

  void applyToken(long v, Robot &robot){
    // Menus:
    // 1: Servo control -> token1=servo(1..8 or 0..7), token2=deg
    // 2: Drive (skate) -> token=speed steps/s (applies to both via driveCmd)
    // 3: Laser -> token 0=off, 1=both on
    // 4: Mode -> 1=stand, 2=sit, 3=pid on, 4=pid off
    // 5: Sound -> 1=loud, 2=quiet, 3=mute
    if (_menu == 0){
      _menu = (int)v;
      _servoSel = -1;
      emitMenu(_menu);
      return;
    }

    if (_menu == 1){
      if (_servoSel < 0){
        _servoSel = normalizeServoIndex(v);
        emitEvent("servo_sel", _servoSel);
        return;
      }
      float deg = (float)constrain(v, 0, 180);
      robot.writeServoLimited(_servoSel, deg);
      emitEvent("servo_set", _servoSel, (long)deg);
#if BUZZER_ENABLED
      g_buzzer.beepOn(g_buzzerDefaultOut, 2400, 40);
#endif
      return;
    }

    if (_menu == 2){
      robot.setDriveCmd((float)v);
      emitEvent("drive", v);
      return;
    }

    if (_menu == 3){
#if LASER_ENABLED
      if (v == 1){ g_lasers.bothOn(); emitEvent("laser", 1); }
      else { g_lasers.off(); emitEvent("laser", 0); }
#else
      emitEvent("laser_disabled");
#endif
      return;
    }

    if (_menu == 4){
      if (v == 1){ robot.setModeStand(); emitEvent("stand"); return; }
      if (v == 2){ robot.setModeSit(); emitEvent("sit"); return; }
      if (v == 3){ robot.setBalance(true); emitEvent("pid", 1); return; }
      if (v == 4){ robot.setBalance(false); emitEvent("pid", 0); return; }
      emitEvent("mode_unknown", v);
      return;
    }

    if (_menu == 5){
#if BUZZER_ENABLED
      if (v == 1){ g_buzzerDefaultOut = BUZZER_OUT_LOUD; g_song.setDefaultOut(g_buzzerDefaultOut); emitEvent("sound_out", 1); g_buzzer.beepOn(g_buzzerDefaultOut, 2200, 60); return; }
      if (v == 2){ g_buzzerDefaultOut = BUZZER_OUT_QUIET; g_song.setDefaultOut(g_buzzerDefaultOut); emitEvent("sound_out", 2); g_buzzer.beepOn(g_buzzerDefaultOut, 2200, 60); return; }
#else
      emitEvent("sound_disabled");
#endif
      return;
    }

    emitEvent("menu_unknown", _menu);
  }

  static int normalizeServoIndex(long v){
    // Accept both 1-based (1..8) and 0-based (0..7)
    if (v >= 1 && v <= SERVO_COUNT_TOTAL) return (int)v - 1;
    return (int)constrain(v, 0, SERVO_COUNT_TOTAL-1);
  }

  static void emitMenu(int menu){
    SERIAL_IO.print(F("{\"ok\":true,\"event\":\"ir_menu\",\"id\":"));
    SERIAL_IO.print(menu);
    SERIAL_IO.println(F("}"));
  }

  static void emitEvent(const char *name){
    SERIAL_IO.print(F("{\"ok\":true,\"event\":\"ir\",\"name\":\""));
    SERIAL_IO.print(name);
    SERIAL_IO.println(F("\"}"));
  }
  static void emitEvent(const char *name, long v){
    SERIAL_IO.print(F("{\"ok\":true,\"event\":\"ir\",\"name\":\""));
    SERIAL_IO.print(name);
    SERIAL_IO.print(F("\",\"v\":"));
    SERIAL_IO.print(v);
    SERIAL_IO.println(F("}"));
  }
  static void emitEvent(const char *name, long a, long b){
    SERIAL_IO.print(F("{\"ok\":true,\"event\":\"ir\",\"name\":\""));
    SERIAL_IO.print(name);
    SERIAL_IO.print(F("\",\"a\":"));
    SERIAL_IO.print(a);
    SERIAL_IO.print(F(",\"b\":"));
    SERIAL_IO.print(b);
    SERIAL_IO.println(F("}"));
  }

  int _menu{0};
  int _servoSel{-1};
  bool _capture{false};
  String _token;
  unsigned long _lastDigitMs{0};
};

static IrMenuController g_irMenu;
#endif

void setup(){
  SERIAL_IO.begin(ROBOT_SERIAL_BAUD);
  robot.begin();
  // Auto-load IMU offsets if present
  if (EEPROM.read(EEPROM_ADDR_MAGIC)==EEPROM_MAGIC){ float p,r; EEPROM.get(EEPROM_ADDR_IMU_OFF,p); EEPROM.get(EEPROM_ADDR_IMU_OFF+sizeof(float),r); robot.imu.setOffsets(p,r); }
  Protocol::sendOk("ready");
#if LCD_ENABLED
  g_lcd.begin(); g_lcd.printLine("READY");
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

static void handleJson(const String &line){
  // Very small manual parse for known keys to avoid heavy JSON libs on AVR
  if (line.indexOf("\"cmd\":\"hello\"")>=0){ Protocol::sendOk("hello"); return; }
  if (line.indexOf("\"cmd\":\"hb\"")>=0){ lastHeartbeatMs = millis(); Protocol::sendOk("hb"); return; }
  if (line.indexOf("\"cmd\":\"lcd\"")>=0){
#if LCD_ENABLED
  int p=line.indexOf("\"msg\":\""); if (p>=0){ int e=line.indexOf('"', p+7); String m = (e>p? line.substring(p+7,e):""); g_lcd.printLine(m); Protocol::sendOk("lcd_ok"); }
  else Protocol::sendErr("no_msg");
#else
  Protocol::sendErr("lcd_disabled");
#endif
  return;
  }
  if (line.indexOf("\"cmd\":\"rfid_last\"")>=0){
#if RFID_ENABLED
  String out = String("{\"ok\":true,\"rfid\":\"") + Protocol::escape(g_lastRfid) + "\"}"; SERIAL_IO.println(out);
#else
  Protocol::sendErr("rfid_disabled");
#endif
  return;
  }
  if (line.indexOf("\"cmd\":\"ultra_read\"")>=0){
#if ULTRA_ENABLED
  String out = String("{\"ok\":true,\"cm\":") + (isnan(g_ultraCm)?String("null"):String(g_ultraCm,1)) + "}"; SERIAL_IO.println(out);
#else
  Protocol::sendErr("ultra_disabled");
#endif
  return;
  }
  if (line.indexOf("\"cmd\":\"avoid\"")>=0){
#if ULTRA_ENABLED
  g_avoidEnable = (line.indexOf("\"enable\":true")>=0);
  Protocol::sendOk(g_avoidEnable?"avoid_on":"avoid_off");
#else
  Protocol::sendErr("ultra_disabled");
#endif
  return;
  }
  if (line.indexOf("\"cmd\":\"laser\"")>=0){
#if LASER_ENABLED
    bool both = (line.indexOf("\"both\":true")>=0);
    int p = line.indexOf("\"id\":"); int id = 0; if (p>=0) id = line.substring(p+5).toInt();
    if (line.indexOf("\"on\":true")>=0){
      if (both){ g_lasers.bothOn(); Protocol::sendOk("laser_both_on"); }
      else if (id==1 || id==2){ g_lasers.oneOn((uint8_t)id); Protocol::sendOk("laser_on"); }
      else { Protocol::sendErr("bad_id"); }
    } else {
      g_lasers.off(); Protocol::sendOk("laser_off");
    }
#else
    Protocol::sendErr("laser_disabled");
#endif
    return;
  }

  if (line.indexOf("\"cmd\":\"sound\"")>=0){
#if BUZZER_ENABLED
    // Select default physical buzzer output
    if (line.indexOf("\"out\":\"loud\"")>=0 || line.indexOf("\"mode\":\"loud\"")>=0){ g_buzzerDefaultOut = BUZZER_OUT_LOUD; g_song.setDefaultOut(g_buzzerDefaultOut); Protocol::sendOk("sound_out_loud"); return; }
    if (line.indexOf("\"out\":\"quiet\"")>=0 || line.indexOf("\"mode\":\"quiet\"")>=0){ g_buzzerDefaultOut = BUZZER_OUT_QUIET; g_song.setDefaultOut(g_buzzerDefaultOut); Protocol::sendOk("sound_out_quiet"); return; }
    Protocol::sendErr("bad_out");
#else
    Protocol::sendErr("buzzer_disabled");
#endif
    return;
  }

  if (line.indexOf("\"cmd\":\"buzzer\"")>=0){
#if BUZZER_ENABLED
    int p=line.indexOf("\"freq\":"); int freq=2200; if(p>=0) freq=line.substring(p+7).toInt();
    p=line.indexOf("\"ms\":"); int ms=60; if(p>=0) ms=line.substring(p+5).toInt();
    BuzzerOut out = g_buzzerDefaultOut;
    if (line.indexOf("\"out\":\"loud\"")>=0) out = BUZZER_OUT_LOUD;
    if (line.indexOf("\"out\":\"quiet\"")>=0) out = BUZZER_OUT_QUIET;
    g_buzzer.beepOn(out, (uint16_t)freq, (uint16_t)ms);
    Protocol::sendOk("beep");
#else
    Protocol::sendErr("buzzer_disabled");
#endif
    return;
  }

    if (line.indexOf("\"cmd\":\"sound_play\"")>=0){
  #if BUZZER_ENABLED
    // {"cmd":"sound_play","name":"walle|bb8","out":"loud|quiet"}
    int p=line.indexOf("\"name\":\"");
    String name = "";
    if (p>=0){ int e=line.indexOf('"', p+8); if (e>p) name = line.substring(p+8, e); }
    BuzzerOut out = g_buzzerDefaultOut;
    if (line.indexOf("\"out\":\"loud\"")>=0) out = BUZZER_OUT_LOUD;
    if (line.indexOf("\"out\":\"quiet\"")>=0) out = BUZZER_OUT_QUIET;
    if (name.length()==0){ Protocol::sendErr("no_name"); return; }
    g_song.play(name, out);
    Protocol::sendOk("sound_play");
  #else
    Protocol::sendErr("buzzer_disabled");
  #endif
    return;
    }
  if (line.indexOf("\"cmd\":\"set_servo\"")>=0){
    int idx=-1; float deg=90;
    int p=line.indexOf("\"index\":"); if(p>=0){ idx=line.substring(p+8).toInt(); }
    p=line.indexOf("\"deg\":"); if(p>=0){ deg=line.substring(p+6).toFloat(); }
    if (idx>=0 && idx<SERVO_COUNT_TOTAL){ robot.writeServoLimited(idx,deg); Protocol::sendOk(); }
    else Protocol::sendErr("bad_index");
    return;
  }
  if (line.indexOf("\"cmd\":\"set_pose\"")>=0){
    // Expect pose as 8 ints [..]; optional duration_ms for time-based easing
    int lb=line.indexOf('['); int rb=line.indexOf(']');
    if (lb>0 && rb>lb){
      uint8_t pose[SERVO_COUNT_TOTAL]; int i=0; String nums=line.substring(lb+1,rb);
      nums += ','; int s=0; for (int k=0;k<nums.length() && i<SERVO_COUNT_TOTAL;k++) if(nums[k]==','){ pose[i++]= (uint8_t) constrain(nums.substring(s,k).toInt(),0,180); s=k+1; }
      // duration_ms
      long durMs = 0; int p=line.indexOf("\"duration_ms\":"); if(p>=0) durMs = line.substring(p+14).toInt();
      if (i==SERVO_COUNT_TOTAL){
        if (durMs>0){
          // Compute max delta and set speed so that worst joint arrives in durMs
          float maxDelta = 0.0f;
          for (int j=0;j<SERVO_COUNT_TOTAL;j++){
            float d = fabs((float)pose[j] - robot.servos.get(j)); if (d>maxDelta) maxDelta=d;
          }
          if (maxDelta>0){ float speed = (maxDelta / (durMs/1000.0f)); robot.servos.setSpeed(speed); }
        }
        robot.writePoseLimited(pose); Protocol::sendOk(); return;
      }
    }
    Protocol::sendErr("bad_pose"); return;
  }
  if (line.indexOf("\"cmd\":\"leg_ik\"")>=0){
    float x=120; Side side=LEFT;
    int p=line.indexOf("\"x\":"); if(p>=0){ x=line.substring(p+4).toFloat(); }
    p=line.indexOf("\"side\":\"R\""); if(p>=0){ side=RIGHT; }
    if (robot.setLegByIK(side,x)) Protocol::sendOk(); else Protocol::sendErr("ik_fail");
    return;
  }
  if (line.indexOf("\"cmd\":\"stepper\"")>=0){
    // modes: pos, vel
    bool vel = line.indexOf("\"mode\":\"vel\"")>=0;
    int id = (line.indexOf("\"id\":1")>=0)?1:0;
    long val=0; int p=line.indexOf("\"value\":"); if(p>=0){ val=line.substring(p+8).toInt(); }
    if (vel){ robot.steppers.setSpeedOne(id, (float)val); }
    else { robot.steppers.moveToOne(id, val); }
    // Optional: global drive override for sit/skate balance blending
    int pd=line.indexOf("\"drive\":"); if(pd>=0){ long d=line.substring(pd+8).toInt(); robot.setDriveCmd((float)d); }
    Protocol::sendOk(); return;
  }
  if (line.indexOf("\"cmd\":\"home\"")>=0){
    robot.steppers.homeBoth(); Protocol::sendOk("homed"); return;
  }
  if (line.indexOf("\"cmd\":\"zero_now\"")>=0){ robot.steppers.zeroNow(); Protocol::sendOk("zeroed_now"); return; }
  if (line.indexOf("\"cmd\":\"zero_set\"")>=0){
    long p1=0,p2=0; int p=line.indexOf("\"p1\":"); if(p>=0) p1=line.substring(p+5).toInt(); p=line.indexOf("\"p2\":"); if(p>=0) p2=line.substring(p+5).toInt();
    robot.steppers.zeroSet(p1,p2); Protocol::sendOk("zero_set"); return;
  }
  if (line.indexOf("\"cmd\":\"stepper_cfg\"")>=0){
    int p=line.indexOf("\"maxSpeed\":"); if(p>=0){ float v=line.substring(p+11).toFloat(); robot.steppers.setMaxSpeed(v); }
    p=line.indexOf("\"accel\":"); if(p>=0){ float a=line.substring(p+8).toFloat(); robot.steppers.setAcceleration(a); }
    Protocol::sendOk("stepper_cfg"); return;
  }
  if (line.indexOf("\"cmd\":\"pid\"")>=0){
    bool enable = (line.indexOf("\"enable\":true")>=0);
    robot.setBalance(enable);
    Protocol::sendOk(enable?"pid_on":"pid_off");
    return;
  }
  if (line.indexOf("\"cmd\":\"calibrate\"")>=0){
    robot.calibrateNeutral();
    Protocol::sendOk("calibrated");
    return;
  }
  if (line.indexOf("\"cmd\":\"stand\"")>=0){ robot.setModeStand(); Protocol::sendOk("stand"); return; }
  if (line.indexOf("\"cmd\":\"sit\"")>=0){ robot.setModeSit(); Protocol::sendOk("sit"); return; }
  if (line.indexOf("\"cmd\":\"imu_read\"")>=0){ robot.imu.read();
    String msg = String("pitch=")+robot.imu.getPitch()+",roll="+robot.imu.getRoll(); Protocol::sendOk(msg); return; }
  if (line.indexOf("\"cmd\":\"imu_cal\"")>=0){ robot.imu.calibrateLevel(); Protocol::sendOk("imu_calibrated"); return; }
  if (line.indexOf("\"cmd\":\"drive\"")>=0){
    long v=0; int p=line.indexOf("\"value\":"); if(p>=0){ v=line.substring(p+8).toInt(); }
    robot.setDriveCmd((float)v); Protocol::sendOk("drive_set"); return;
  }
  if (line.indexOf("\"cmd\":\"eeprom_save\"")>=0){
    float p,r; robot.imu.getOffsets(p,r);
    EEPROM.update(EEPROM_ADDR_MAGIC, EEPROM_MAGIC);
    EEPROM.put(EEPROM_ADDR_IMU_OFF, p); EEPROM.put(EEPROM_ADDR_IMU_OFF+sizeof(float), r);
    Protocol::sendOk("saved"); return;
  }
  if (line.indexOf("\"cmd\":\"eeprom_load\"")>=0){
    if (EEPROM.read(EEPROM_ADDR_MAGIC)==EEPROM_MAGIC){ float p,r; EEPROM.get(EEPROM_ADDR_IMU_OFF,p); EEPROM.get(EEPROM_ADDR_IMU_OFF+sizeof(float),r); robot.imu.setOffsets(p,r); Protocol::sendOk("loaded"); }
    else Protocol::sendErr("no_data");
    return;
  }
  if (line.equalsIgnoreCase("cal")) { robot.calibrateNeutral(); Protocol::sendOk("calibrated"); return; }
  if (line.indexOf("\"cmd\":\"policy\"")>=0){
    // MuJoCo/policy hook: optional pose[8] and steppers[2] arrays
    int lb=line.indexOf("[", line.indexOf("\"pose\""));
    int rb=line.indexOf("]", lb+1);
    if (lb>0 && rb>lb){ uint8_t pose[SERVO_COUNT_TOTAL]; int i=0; String nums=line.substring(lb+1,rb); nums+=','; int s=0; for(int k=0;k<nums.length() && i<SERVO_COUNT_TOTAL;k++) if(nums[k]==','){ pose[i++]=(uint8_t)constrain(nums.substring(s,k).toInt(),0,180); s=k+1; }
      if (i==SERVO_COUNT_TOTAL) robot.servos.writePose(pose);
    }
    int ls=line.indexOf("[", line.indexOf("\"steppers\""));
    int rs=line.indexOf("]", ls+1);
    if (ls>0 && rs>ls){ String nums=line.substring(ls+1,rs); nums+=','; long v[2]={0,0}; int i=0; int s=0; for(int k=0;k<nums.length() && i<2;k++) if(nums[k]==','){ v[i++]=nums.substring(s,k).toInt(); s=k+1; }
      if (i>=1) robot.steppers.setSpeedOne(0, (float)v[0]);
      if (i>=2) robot.steppers.setSpeedOne(1, (float)v[1]);
    }
    Protocol::sendOk("policy_applied"); return;
  }
  if (line.indexOf("\"cmd\":\"track\"")>=0){
    // Tracking skeleton: client (OpenCV) sends desired head angles and optional steer velocity
    // {"cmd":"track","head_tilt":x,"head_pan":y,"drive":v}
    float tilt=90, pan=90; long drive=0;
    int p=line.indexOf("\"head_tilt\":"); if(p>=0) tilt=line.substring(p+12).toFloat();
    p=line.indexOf("\"head_pan\":"); if(p>=0) pan=line.substring(p+11).toFloat();
    p=line.indexOf("\"drive\":"); if(p>=0) drive=line.substring(p+9).toInt();
    robot.head(tilt, pan);
    // In sit/skate, set user drive command (mixed with balance correction)
    robot.setDriveCmd((float)drive);
    Protocol::sendOk("track_ack"); return;
  }
  if (line.indexOf("\"cmd\":\"get_state\"")>=0){
    robot.imu.read();
    String out = "{""ok"":true,""mode"":"; out += (robot.getMode()==MODE_STAND?"\"stand\"":"\"sit\"");
    out += ",""pid"":"; out += (robot.isBalanceEnabled()?"true":"false");
    out += ",""pitch"":"; out += robot.imu.getPitch();
    out += ",""roll"":"; out += robot.imu.getRoll();
    out += ",""pose"": [";
    for (int i=0;i<SERVO_COUNT_TOTAL;i++){ if(i) out += ","; out += (int)robot.servos.get(i); }
    out += "],""stepper_pos"": ["; out += robot.steppers.pos1(); out += ","; out += robot.steppers.pos2(); out += "]}";
    SERIAL_IO.println(out); return;
  }
  if (line.indexOf("\"cmd\":\"estop\"")>=0){
    robot.estop();
#if BUZZER_ENABLED
    g_buzzer.beepOn(BUZZER_OUT_LOUD, 1800, 150);
#endif
    Protocol::sendOk("estopped");
    return;
  }
  if (line.indexOf("\"cmd\":\"telemetry_start\"")>=0){
    int p=line.indexOf("\"interval_ms\":"); if(p>=0){ unsigned long v=line.substring(p+15).toInt(); telemetryInterval = max((unsigned long)TELEMETRY_MIN_INTERVAL_MS, v); }
    telemetryOn = true; lastTelemetryMs = millis(); Protocol::sendOk("telemetry_on"); return;
  }
  if (line.indexOf("\"cmd\":\"telemetry_stop\"")>=0){ telemetryOn=false; Protocol::sendOk("telemetry_off"); return; }
  if (line.indexOf("\"cmd\":\"tune\"")>=0){
    int p=line.indexOf("\"servo_speed\":"); if(p>=0){ float v=line.substring(p+14).toFloat(); robot.setServoSpeed(v); }
    float kpP,kiP,kdP,kpR,kiR,kdR; robot.getPidGains(kpP,kiP,kdP,kpR,kiR,kdR);
    p=line.indexOf("\"kpP\":"); if(p>=0) kpP=line.substring(p+6).toFloat();
    p=line.indexOf("\"kiP\":"); if(p>=0) kiP=line.substring(p+6).toFloat();
    p=line.indexOf("\"kdP\":"); if(p>=0) kdP=line.substring(p+6).toFloat();
    p=line.indexOf("\"kpR\":"); if(p>=0) kpR=line.substring(p+6).toFloat();
    p=line.indexOf("\"kiR\":"); if(p>=0) kiR=line.substring(p+6).toFloat();
    p=line.indexOf("\"kdR\":"); if(p>=0) kdR=line.substring(p+6).toFloat();
    robot.setPidGains(kpP,kiP,kdP,kpR,kiR,kdR);
    float skp, ski, skd; robot.getSkateGains(skp,ski,skd); float smax=robot.getSkateSpeedLimit();
    int sp=line.indexOf("\"skate\""); if(sp>=0){
      int q=line.indexOf("\"kp\":", sp); if(q>0) skp=line.substring(q+5).toFloat();
      q=line.indexOf("\"ki\":", sp); if(q>0) ski=line.substring(q+5).toFloat();
      q=line.indexOf("\"kd\":", sp); if(q>0) skd=line.substring(q+5).toFloat();
      q=line.indexOf("\"max\":", sp); if(q>0) smax=line.substring(q+6).toFloat();
    }
    robot.setSkateGains(skp,ski,skd); robot.setSkateSpeedLimit(smax);
    Protocol::sendOk("tuned"); return;
  }
  Protocol::sendErr("unknown_cmd");
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
      g_lcd.printLine("RFID:" + tail);
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
        g_lcd.printLine("AVOID:" + String((int)g_ultraCm) + "cm");
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

#if BUZZER_ENABLED
  g_song.update();
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
