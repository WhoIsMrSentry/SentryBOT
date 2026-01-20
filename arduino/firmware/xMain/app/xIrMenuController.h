#ifndef SENTRY_APP_IR_MENU_CONTROLLER_H
#define SENTRY_APP_IR_MENU_CONTROLLER_H

#include <Arduino.h>
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
    // Feedback beep for every valid key
    // Short, high pitch
    g_buzzer.beepOn(g_buzzerDefaultOut, 2400, 30);
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
      if (k == "UP"){ robot.setModeStand(); emitEvent("stand"); lcdPrint("MODE", "STAND"); return; }
      if (k == "DOWN"){ robot.setModeSit(); emitEvent("sit"); lcdPrint("MODE", "SIT"); return; }
      if (k == "LEFT"){ robot.setDriveCmd(-200); emitEvent("drive", -200); lcdPrint("DRIVE", "-200"); return; }
      if (k == "RIGHT"){ robot.setDriveCmd(200); emitEvent("drive", 200); lcdPrint("DRIVE", "200"); return; }
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

    // NeoPixel flow
    if (_state >= STATE_NEO_MAIN && _state <= STATE_NEO_ANIM){
      if (k == "*"){
        startToken();
        showNeoPixelToken();
        return;
      }
      if (k == "OK"){
        commitTokenIfAny(robot);
        _capture = false;
        _token = "";
        showNeoPixelPrompt();
        return;
      }
      if (isDigitKey(k)){
        if (!_capture){
          _capture = true;
          _token = "";
        }
        _token += k;
        _lastDigitMs = millis();
        showNeoPixelToken();
        return;
      }
      return;
    }

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
      if (k == "LEFT" || k == "RIGHT"){
#if BUZZER_ENABLED
        // Toggle output
        g_buzzerDefaultOut = (g_buzzerDefaultOut == BUZZER_OUT_LOUD) ? BUZZER_OUT_QUIET : BUZZER_OUT_LOUD;
        g_song.setDefaultOut(g_buzzerDefaultOut);
#endif
        showSound();
        return;
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
      if (millis() - _lastDigitMs >= (unsigned long)IR_TOKEN_TIMEOUT_MS){
        commitTokenIfAny(robot);
        _capture = false;
        _token = "";
        showServoPrompt();
      }
    }

    if (_capture && _token.length() > 0 && _lastDigitMs != 0 && _state >= STATE_NEO_MAIN){
      if (millis() - _lastDigitMs >= (unsigned long)IR_TOKEN_TIMEOUT_MS){
        commitTokenIfAny(robot);
        _capture = false;
        _token = "";
        showNeoPixelPrompt();
      }
    }

    // Periodic refresh for live pages
    if (_state == STATE_ULTRA || _state == STATE_IMU || _state == STATE_RFID || _state == STATE_SYSTEM || _state == STATE_LASER){
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
        g_buzzer.beepOn(g_buzzerDefaultOut, 2800, 30);
      }
    }
#endif

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
    STATE_NEO_MAIN,
    STATE_NEO_RGB_R,
    STATE_NEO_RGB_G,
    STATE_NEO_RGB_B,
    STATE_NEO_ANIM,
  };

  enum MenuItem : uint8_t {
    MENU_SERVO = 0,
    MENU_LASER,
    MENU_ULTRA,
    MENU_IMU,
    MENU_RFID,
    MENU_SOUND,
    MENU_NEOPIXEL,
    MENU_SYSTEM,
    MENU_COUNT,
  };

  enum SoundItem : uint8_t {
    SOUND_WALLE = 0,
    SOUND_BB8,
    SOUND_MORSE,
    SOUND_BUZZER,
    SOUND_COUNT,
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
      case MENU_NEOPIXEL: return "NEOPIXEL";
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
        showSound();
        return;

      case MENU_SYSTEM:
        _state = STATE_SYSTEM;
        _lastUiMs = 0;
        refreshLive(robot);
        return;

      case MENU_NEOPIXEL:
        _state = STATE_NEO_MAIN;
        _neoR = 255; _neoG = 50; _neoB = 255; // Default from user request
        _capture = false;
        _token = "";
        _lastDigitMs = 0;
        showNeoPixelPrompt();
        return;

      default:
        return;
    }
  }

  void showServoPrompt();
  void showServoToken();
  void showNeoPixelPrompt();
  void showNeoPixelToken();

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
  void applyToken(long v, Robot &robot);

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

  uint8_t _neoR{255}, _neoG{255}, _neoB{255};
  unsigned long _lastProxBeepMs{0};
};

#include "menus/xIrMenuController_sound.h"
#include "menus/xIrMenuController_servo.h"
#include "menus/xIrMenuController_neopixel.h"
#include "menus/xIrMenuController_sensors.h"

#endif // IR_ENABLED

#endif // SENTRY_APP_IR_MENU_CONTROLLER_H
