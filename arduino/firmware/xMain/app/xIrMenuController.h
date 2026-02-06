#ifndef SENTRY_APP_IR_MENU_CONTROLLER_H
#define SENTRY_APP_IR_MENU_CONTROLLER_H

#include <Arduino.h>
#include <EEPROM.h>
#include "../xConfig.h"
#include "../xRobot.h"

#if IR_ENABLED

#if LCD_ENABLED
#include "xLcdHub.h"
#endif

#if BUZZER_ENABLED
#include "../xPeripherals.h"
extern BuzzerPair g_buzzer;
extern BuzzerSongPlayer g_song;
extern BuzzerOut g_buzzerDefaultOut;
extern bool g_buzzerBothEnabled;
extern uint16_t g_buzzerFreqLoud;
extern uint16_t g_buzzerFreqQuiet;
#endif

#if LASER_ENABLED
#include "../xPeripherals.h"
extern LaserPair g_lasers;
#endif

#if ULTRA_ENABLED
extern float g_ultraCm;
#endif

#if RFID_ENABLED
extern String g_lastRfid;
#endif

#if LCD_ENABLED
extern bool g_lcd1Ok;
extern uint8_t g_lcdRouteMask;
#if LCD2_ENABLED
extern bool g_lcd2Ok;
#endif
#endif

class IrMenuController {
public:
  void reset(){
    _state = STATE_HOME;
    _menuIndex = 0;
    _token = "";
    _capture = false;
    _lastDigitMs = 0;
    _servoSel = -1;
    _laserMode = 0;
    _lastUiMs = 0;
    _imuSub = 0;

    _sysSub = 0;

    _soundIndex = 0;
    _morseMode = false;
    _morsePattern = "";
    _morseIdx = 0;
    _morseNextMs = 0;
    _morsePlaying = false;
    _lastProxBeepMs = 0;
    showHome();
  }

#if LCD_ENABLED
  typedef void (*LcdPrintFn)(const String &, const String &);
  void setLcdPrint(LcdPrintFn fn){ _lcdPrint = fn; }
#endif

  void onKey(const String &k, Robot &robot){
    if (k == "UNKNOWN") return;

#if BUZZER_ENABLED
  // Feedback beep for every valid key — use per-buzzer frequencies; both optional
  if (g_buzzerBothEnabled){
    g_buzzer.beepOn(BUZZER_OUT_LOUD, g_buzzerFreqLoud, 30);
    g_buzzer.beepOn(BUZZER_OUT_QUIET, g_buzzerFreqQuiet, 30);
  } else {
    uint16_t f = (g_buzzerDefaultOut == BUZZER_OUT_LOUD) ? g_buzzerFreqLoud : g_buzzerFreqQuiet;
    g_buzzer.beepOn(g_buzzerDefaultOut, f, 30);
  }
#endif

    // Global back/cancel
    if (k == "#"){
      if (_capture){
        cancelToken();
        lcdPrint("TOKEN", "CANCEL");
        return;
      }
      if (_state == STATE_SERVO_DEG){
        _state = STATE_SERVO_SEL;
        _servoSel = -1;
        showServoPrompt();
        return;
      }
      if (_state != STATE_HOME){
        enterHome();
        return;
      }
      // already home
      showHome();
      return;
    }

    // HOME: keep simple direct controls; OK opens menu
    if (_state == STATE_HOME){
      if (k == "OK"){
        enterMenu();
        return;
      }
      // Replace stand/sit animations with position-based stepper moves
      if (k == "LEFT"){
        // Steering left: move both tracks forward but inner (left) wheel fewer steps
        float revs_per_deg = STEPPER_STEPS_PER_REV / 360.0f;
        long outer_steps = (long)(STEERING_FORWARD_DEG * revs_per_deg);
        long inner_steps = (long)(outer_steps * STEERING_INNER_SCALE);
        // both forward, left inner slower
        robot.steppers.moveByOne(0, inner_steps);
        robot.steppers.moveByOne(1, outer_steps);
        lcdPrint("TURN", "LEFT"); emitEvent("steer", -1);
        return;
      }
      if (k == "RIGHT"){
        float revs_per_deg = STEPPER_STEPS_PER_REV / 360.0f;
        long outer_steps = (long)(STEERING_FORWARD_DEG * revs_per_deg);
        long inner_steps = (long)(outer_steps * STEERING_INNER_SCALE);
        // both forward, right inner slower
        robot.steppers.moveByOne(0, outer_steps);
        robot.steppers.moveByOne(1, inner_steps);
        lcdPrint("TURN", "RIGHT"); emitEvent("steer", 1);
        return;
      }
      if (k == "DOWN"){
        // Move backward a short distance
        float revs_per_deg = STEPPER_STEPS_PER_REV / 360.0f;
        long steps = (long)(STEERING_FORWARD_DEG * revs_per_deg);
        robot.steppers.moveByOne(0, -steps);
        robot.steppers.moveByOne(1, -steps);
        lcdPrint("DRIVE", "BACK"); emitEvent("drive", -100);
        return;
      }
      if (k == "UP"){
        // Move forward a short distance
        float revs_per_deg = STEPPER_STEPS_PER_REV / 360.0f;
        long steps = (long)(STEERING_FORWARD_DEG * revs_per_deg);
        robot.steppers.moveByOne(0, steps);
        robot.steppers.moveByOne(1, steps);
        lcdPrint("DRIVE", "FORWARD"); emitEvent("drive", 100);
        return;
      }
      // digits on home just show key feedback
      lcdPrint("IR", "KEY:" + k);
      return;
    }

    // MENU: UP/DOWN select, OK enter
    if (_state == STATE_MENU){
      if (k == "UP"){ menuPrev(); showMenu(); return; }
      if (k == "DOWN"){ menuNext(); showMenu(); return; }
      if (k == "OK"){ enterSelected(robot); return; }
      // ignore others
      return;
    }

    // Servo flow
    if (_state == STATE_SERVO_SEL || _state == STATE_SERVO_DEG){
      if (k == "*"){
        startToken();
        showServoToken();
        return;
      }
      if (k == "OK"){
        commitTokenIfAny(robot);
        _capture = false;
        _token = "";
        showServoPrompt();
        return;
      }
      if (isDigitKey(k)){
        if (!_capture){
          _capture = true;
          _token = "";
        }
        _token += k;
        _lastDigitMs = millis();
        showServoToken();
        return;
      }
      return;
    }

    // NeoPixel support removed

    // Laser control
    if (_state == STATE_LASER){
      if (k == "OK" || k == "UP"){
        _laserMode = (_laserMode + 1) % 4;
        applyLaser();
        showLaser();
        return;
      }
      if (k == "DOWN"){
        if (_laserMode == 0) _laserMode = 3;
        else _laserMode--;
        applyLaser();
        showLaser();
        return;
      }
      return;
    }


    // Sound / buzzer
    if (_state == STATE_SOUND){
      // LEFT: toggle default output (LOUD/QUIET)
      if (k == "LEFT"){
#if BUZZER_ENABLED
        g_buzzerDefaultOut = (g_buzzerDefaultOut == BUZZER_OUT_LOUD) ? BUZZER_OUT_QUIET : BUZZER_OUT_LOUD;
        g_song.setDefaultOut(g_buzzerDefaultOut);
#endif
        showSound();
        return;
      }

      // RIGHT: when on BUZZER entry, toggle both buzzers; otherwise toggle output
      if (k == "RIGHT"){
        if (_soundIndex == SOUND_BUZZER || _soundIndex == SOUND_BUZZER_SETTINGS){
          // when in buzzer area, RIGHT toggles selected buzzer between LOUD/QUIET for adjustment
          _buzzerSel = (_buzzerSel == SEL_BUZZER_LOUD) ? SEL_BUZZER_QUIET : SEL_BUZZER_LOUD;
          showSound();
          return;
        } else {
#if BUZZER_ENABLED
          g_buzzerDefaultOut = (g_buzzerDefaultOut == BUZZER_OUT_LOUD) ? BUZZER_OUT_QUIET : BUZZER_OUT_LOUD;
          g_song.setDefaultOut(g_buzzerDefaultOut);
#endif
          showSound();
          return;
        }
      }

      // STAR '*' enters/exits freq-adjust mode when on BUZZER or BUZZER_SETTINGS
      if (k == "*" && (_soundIndex == SOUND_BUZZER || _soundIndex == SOUND_BUZZER_SETTINGS)){
        _freqAdjustMode = !_freqAdjustMode;
        _buzzerNumCapture = false;
        _buzzerNumToken = "";
        if (!_freqAdjustMode){
#if BUZZER_ENABLED
          EEPROM.put(EEPROM_ADDR_BUZZER_FREQ_LOUD, g_buzzerFreqLoud);
          EEPROM.put(EEPROM_ADDR_BUZZER_FREQ_QUIET, g_buzzerFreqQuiet);
          EEPROM.update(EEPROM_ADDR_BUZZER_FREQ_MAGIC, EEPROM_BUZZER_MAGIC);
#endif
          lcdPrint("SOUND", "FREQ SAVED");
        } else {
          showSound();
        }
        return;
      }

      // If in freq-adjust mode, handle numeric entry and exit by '#'
      if (_freqAdjustMode){
        if (k == "#"){
          // exit and persist
#if BUZZER_ENABLED
          EEPROM.put(EEPROM_ADDR_BUZZER_FREQ_LOUD, g_buzzerFreqLoud);
          EEPROM.put(EEPROM_ADDR_BUZZER_FREQ_QUIET, g_buzzerFreqQuiet);
          EEPROM.update(EEPROM_ADDR_BUZZER_FREQ_MAGIC, EEPROM_BUZZER_MAGIC);
#endif
          _freqAdjustMode = false; _buzzerNumCapture = false; _buzzerNumToken = ""; showSound(); return;
        }

        if (_buzzerNumCapture){
          // collect digits; OK commits
          if (isDigitKey(k)){
            _buzzerNumToken += k;
            lcdPrint("NUM:" , _buzzerNumToken);
            return;
          }
          if (k == "OK"){
            long v = _buzzerNumToken.toInt();
            if (v >= 200 && v <= 4000){
              if (_buzzerSel == SEL_BUZZER_LOUD) g_buzzerFreqLoud = (uint16_t)v;
              else g_buzzerFreqQuiet = (uint16_t)v;
            }
            _buzzerNumCapture = false; _buzzerNumToken = ""; showSound(); return;
          }
          if (k == "#"){
            _buzzerNumCapture = false; _buzzerNumToken = ""; showSound(); return;
          }
          // ignore others while in numeric capture
          return;
        }

        // '*' during adjust enters numeric capture
        if (k == "*"){
          _buzzerNumCapture = true; _buzzerNumToken = ""; lcdPrint("ENTER NUM","(OK=SAVE)"); return;
        }

        // otherwise UP/DOWN adjust selected buzzer (handled later by existing code path)
      }

      // Normal UP/DOWN navigation when not in freq-adjust mode
      if (_freqAdjustMode){
        // Adjust runtime freq in 100Hz steps for selected buzzer (default selects LOUD)
        int sel = SEL_BUZZER_LOUD; // default
        if (_buzzerSel == SEL_BUZZER_QUIET) sel = SEL_BUZZER_QUIET;
        if (k == "UP"){
          if (sel == SEL_BUZZER_LOUD) g_buzzerFreqLoud = (uint16_t)constrain((int)g_buzzerFreqLoud + 100, 200, 4000);
          else g_buzzerFreqQuiet = (uint16_t)constrain((int)g_buzzerFreqQuiet + 100, 200, 4000);
          showSound();
          return;
        }
        if (k == "DOWN"){
          if (sel == SEL_BUZZER_LOUD) g_buzzerFreqLoud = (uint16_t)constrain((int)g_buzzerFreqLoud - 100, 200, 4000);
          else g_buzzerFreqQuiet = (uint16_t)constrain((int)g_buzzerFreqQuiet - 100, 200, 4000);
          showSound();
          return;
        }
        if (k == "OK"){
#if BUZZER_ENABLED
          if (g_buzzerBothEnabled){
            g_buzzer.beepOn(BUZZER_OUT_LOUD, g_buzzerFreqLoud, 80);
            g_buzzer.beepOn(BUZZER_OUT_QUIET, g_buzzerFreqQuiet, 80);
          } else {
            uint16_t f = (g_buzzerDefaultOut==BUZZER_OUT_LOUD)?g_buzzerFreqLoud:g_buzzerFreqQuiet;
            g_buzzer.beepOn(g_buzzerDefaultOut, f, 80);
          }
#endif
          return;
        }
      }

      if (k == "UP"){
        if (_soundIndex == 0) _soundIndex = SOUND_COUNT - 1;
        else _soundIndex--;
        _morseMode = false;
        showSound();
        return;
      }
      if (k == "DOWN"){
        _soundIndex = (_soundIndex + 1) % SOUND_COUNT;
        _morseMode = false;
        showSound();
        return;
      }

      if (k == "OK"){
        playSelectedSound();
        showSound();
        return;
      }
      if (k == "LEFT" || k == "RIGHT"){
#if BUZZER_ENABLED
        g_buzzerDefaultOut = (g_buzzerDefaultOut == BUZZER_OUT_LOUD) ? BUZZER_OUT_QUIET : BUZZER_OUT_LOUD;
        g_song.setDefaultOut(g_buzzerDefaultOut);
#endif
        showSound();
        return;
      }

      // Morse mode: digits (and OK) produce deterministic patterns.
      if (_morseMode){
        String pat = morsePatternForKey(k);
        if (pat.length() > 0){
          startMorse(pat);
          lcdPrint("MORSE:" + k, pat);
        }
      }
      return;
    }

    // Sensor pages: allow changing subpage on IMU
    if (_state == STATE_IMU){
      if (k == "UP" || k == "DOWN"){
        _imuSub = (_imuSub + 1) % 3;
        _lastUiMs = 0;
      }
      return;
    }

    if (_state == STATE_SYSTEM){
      if (k == "UP" || k == "DOWN"){
        _sysSub = (_sysSub + 1) % 3;
        _lastUiMs = 0;
      }
      return;
    }
  }

  void tick(Robot &robot){
    // Token timeout
    if (_capture && _token.length() > 0 && _lastDigitMs != 0){
      unsigned long now = millis();
      if (_lastUiMs == 0 || (now - _lastUiMs) >= 250UL){
        _lastUiMs = now;
        refreshLive(robot);
      }
    }

    // Proximity feedback in Ultra mode
#if ULTRA_ENABLED && BUZZER_ENABLED
    if (_state == STATE_ULTRA && !isnan(g_ultraCm) && g_ultraCm > 0 && g_ultraCm < 150.0f){
      unsigned long now2 = millis();
      // closer = faster beeps. Interval: ~50ms to 800ms.
      unsigned long interval = (unsigned long)constrain(g_ultraCm * 5.0f + 40.0f, 50.0f, 800.0f);
      if (now2 - _lastProxBeepMs >= interval){
        _lastProxBeepMs = now2;
        if (g_buzzerBothEnabled){
          g_buzzer.beepOn(BUZZER_OUT_LOUD, g_buzzerFreqLoud, 30);
          g_buzzer.beepOn(BUZZER_OUT_QUIET, g_buzzerFreqQuiet, 30);
        } else {
          g_buzzer.beepOn(BUZZER_OUT_LOUD, g_buzzerFreqLoud, 30);
        }
      }
    }
#endif

    // Periodic refresh for live sensor pages (ULTRA/IMU/RFID/SYSTEM)
    unsigned long _now = millis();
    if (_state == STATE_ULTRA || _state == STATE_IMU || _state == STATE_RFID || _state == STATE_SYSTEM){
      if (_lastUiMs == 0 || (_now - _lastUiMs) >= 250UL){
        _lastUiMs = _now;
        refreshLive(robot);
      }
    }

    // Non-blocking morse player
    tickMorse();
  }

  static bool isDigitKey(const String &k){ return k.length() == 1 && k[0] >= '0' && k[0] <= '9'; }

  enum State : uint8_t {
    STATE_HOME = 0,
    STATE_MENU,
    STATE_SERVO_SEL,
    STATE_SERVO_DEG,
    STATE_LASER,
    STATE_SOUND,
    STATE_ULTRA,
    STATE_IMU,
    STATE_RFID,
    STATE_SYSTEM,
  };

  enum MenuItem : uint8_t {
    MENU_SERVO = 0,
    MENU_LASER,
    MENU_ULTRA,
    MENU_IMU,
    MENU_RFID,
    MENU_SOUND,
    MENU_SYSTEM,
    MENU_COUNT,
  };

  enum SoundItem : uint8_t {
    SOUND_WALLE = 0,
    SOUND_BB8,
    SOUND_MORSE,
    SOUND_BUZZER,
    SOUND_BUZZER_SETTINGS,
    SOUND_COUNT,
  };

  enum {
    SEL_BUZZER_LOUD = 0,
    SEL_BUZZER_QUIET = 1
  };

  void enterHome(){
#if LCD_ENABLED
    g_lcdStatus.setPinned(false);
#endif
    _state = STATE_HOME;
    _capture = false;
    _token = "";
    _lastDigitMs = 0;
    _lastUiMs = 0;
    showHome();
  }

  void enterMenu(){
#if LCD_ENABLED
    g_lcdStatus.setPinned(true);
#endif
    _state = STATE_MENU;
    _capture = false;
    _token = "";
    _lastDigitMs = 0;
    showMenu();
  }

  void menuPrev(){
    if (_menuIndex == 0) _menuIndex = MENU_COUNT - 1;
    else _menuIndex--;
  }
  void menuNext(){
    _menuIndex = (_menuIndex + 1) % MENU_COUNT;
  }

  static String menuName(uint8_t idx){
    switch ((MenuItem)idx){
      case MENU_SERVO: return "SERVO";
      case MENU_LASER: return "LASER";
      case MENU_ULTRA: return "ULTRA";
      case MENU_IMU: return "IMU";
      case MENU_RFID: return "RFID";
      case MENU_SOUND: return "SOUND";
      case MENU_SYSTEM: return "SYSTEM";
      default: return "MENU";
    }
  }

  void showHome(){
    lcdPrint("IR", "OK=MENU #=BACK");
  }

  void showMenu(){
    lcdPrint("MENU", menuName(_menuIndex) + " OK=ENTER");
  }

  void enterSelected(Robot &robot){
    switch ((MenuItem)_menuIndex){
      case MENU_SERVO:
        if (!robot.servos.driverOk()){
          lcdPrint("SERVO", "DRIVER MISSING");
          return;
        }
        _state = STATE_SERVO_SEL;
        _servoSel = -1;
        _capture = false;
        _token = "";
        _lastDigitMs = 0;
        showServoPrompt();
        return;

      case MENU_LASER:
        _state = STATE_LASER;
        _lastUiMs = 0;
        showLaser();
        return;

      case MENU_ULTRA:
        _state = STATE_ULTRA;
        _lastUiMs = 0;
        refreshLive(robot);
        return;

      case MENU_IMU:
        _state = STATE_IMU;
        _imuSub = 0;
        _lastUiMs = 0;
        refreshLive(robot);
        return;

      case MENU_RFID:
        _state = STATE_RFID;
        _lastUiMs = 0;
        refreshLive(robot);
        return;

      case MENU_SOUND:
        _state = STATE_SOUND;
        _morseMode = false;
        _lastUiMs = 0;
        _soundIndex = 0;
        showSound();
        return;

      case MENU_SYSTEM:
        _state = STATE_SYSTEM;
        _lastUiMs = 0;
        refreshLive(robot);
        return;

      default:
        return;
    }
  }

  void showServoPrompt();
  void showServoToken();

  void showLaser(){
    const char* modes[] = {"OFF", "L1", "L2", "BOTH"};
    lcdPrint("LASER", String(modes[_laserMode % 4]) + " UP/DN/OK");
  }

  static String soundName(uint8_t idx);
  void showSound();
  void playSelectedSound();
  static String morsePatternForKey(const String &k);
  void startMorse(const String &pattern);
  String textToMorse(const String &text);
  void tickMorse();

  void applyLaser(){
#if LASER_ENABLED
    if (_laserMode == 1) g_lasers.oneOn(1);
    else if (_laserMode == 2) g_lasers.oneOn(2);
    else if (_laserMode == 3) g_lasers.bothOn();
    else g_lasers.off();
#endif
  }

  void startToken();
  void cancelToken();
  void commitTokenIfAny(Robot &robot);
  void applyToken(long v, Robot &robot){
    if (_state == STATE_SERVO_SEL){
      _servoSel = normalizeServoIndex(v);
      emitEvent("servo_sel", _servoSel);
      _state = STATE_SERVO_DEG;
      showServoPrompt();
      return;
    }
    if (_state == STATE_SERVO_DEG){
      float deg = (float)constrain(v, 0, 180);
      robot.writeServoLimited(_servoSel, deg);
      emitEvent("servo_set", _servoSel, (long)deg);
      lcdPrint("SERVO:" + String(_servoSel + 1), "DEG:" + String((int)deg));
#if BUZZER_ENABLED
    if (g_buzzerBothEnabled){
      g_buzzer.beepOn(BUZZER_OUT_LOUD, g_buzzerFreqLoud, 40);
      g_buzzer.beepOn(BUZZER_OUT_QUIET, g_buzzerFreqQuiet, 40);
    } else g_buzzer.beepOn(BUZZER_OUT_LOUD, g_buzzerFreqLoud, 40);
#endif
      return;
    }
    // NeoPixel support removed
  }

#if LCD_ENABLED
  void lcdPrint(const String &top, const String &bottom = ""){
    if (_lcdPrint) _lcdPrint(top, bottom);
  }
  LcdPrintFn _lcdPrint{nullptr};
#else
  void lcdPrint(const String &, const String & = ""){ }
#endif

  void refreshLive(Robot &robot);

private:

  static int normalizeServoIndex(long v){
    // Accept both 1-based (1..8) and 0-based (0..7)
    return (int)constrain(v, 0, SERVO_COUNT_TOTAL - 1);
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

  State _state{STATE_HOME};
  uint8_t _menuIndex{0};

  int _servoSel{-1};
  uint8_t _laserMode{0}; // 0:OFF, 1:L1, 2:L2, 3:BOTH

  bool _capture{false};
  String _token;
  unsigned long _lastDigitMs{0};

  unsigned long _lastUiMs{0};
  uint8_t _imuSub{0};

  uint8_t _sysSub{0};

  uint8_t _soundIndex{0};
  bool _morseMode{false};
  String _morsePattern;
  uint16_t _morseIdx{0};
  unsigned long _morseNextMs{0};
  bool _morsePlaying{false};

  bool _freqAdjustMode{false};
  uint8_t _buzzerSel{SEL_BUZZER_LOUD};
  bool _buzzerNumCapture{false};
  String _buzzerNumToken{""};

  // NeoPixel state removed
  unsigned long _lastProxBeepMs{0};
  // rotation timeout removed; moves are now position-based
};

#include "menus/xIrMenuController_sound.h"
#include "menus/xIrMenuController_servo.h"
#include "menus/xIrMenuController_sensors.h"

#endif // IR_ENABLED

#endif // SENTRY_APP_IR_MENU_CONTROLLER_H
