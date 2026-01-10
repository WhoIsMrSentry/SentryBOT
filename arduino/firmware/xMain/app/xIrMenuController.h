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

// IR command state machine: tokens are entered as "*<digits>" and committed either by
// - waiting IR_TOKEN_TIMEOUT_MS with no new digits, or
// - pressing '*' again, or
// - pressing 'OK' / '#'
// Example flow: *1 (menu=1 servo), *4 (servo=4), *90 (angle=90)
class IrMenuController {
public:
  void reset(){ _menu = 0; _servoSel = -1; _token = ""; _capture = false; _lastDigitMs = 0; }

#if LCD_ENABLED
  typedef void (*LcdPrintFn)(const String &, const String &);
  void setLcdPrint(LcdPrintFn fn){ _lcdPrint = fn; }
#endif

  void onKey(const String &k, Robot &robot){
    if (k == "UNKNOWN") return;

    // Always show received key (when not in a capture flow) so user knows IR is working.
    if (!_capture){
      if (_menu == 0){
        lcdPrint("IR", "KEY:" + k);
      } else {
        lcdPrint(menuTop(), "KEY:" + k);
      }
    }

    // Direct controls (no menu needed)
    if (!_capture && _menu == 0){
      if (k == "UP"){ robot.setModeStand(); emitEvent("stand"); lcdPrint("MODE:STAND"); return; }
      if (k == "DOWN"){ robot.setModeSit(); emitEvent("sit"); lcdPrint("MODE:SIT"); return; }
      if (k == "LEFT"){ robot.setDriveCmd(-200); emitEvent("drive", -200); lcdPrint("DRIVE:-200"); return; }
      if (k == "RIGHT"){ robot.setDriveCmd(200); emitEvent("drive", 200); lcdPrint("DRIVE:200"); return; }
      if (k == "OK"){ robot.setDriveCmd(0); emitEvent("drive", 0); lcdPrint("DRIVE:0"); return; }
    }

    // Back / cancel
    if (k == "#"){
      // If currently typing a token, cancel it.
      if (_capture){
        _capture = false;
        _token = "";
        _lastDigitMs = 0;
        lcdPrint("TOKEN", "CANCEL");
        return;
      }

      // If in a submenu stage, go one step back.
      if (_menu == 1 && _servoSel >= 0){
        _servoSel = -1;
        lcdPrint(menuTop(), "SERVO? (1..8)");
        return;
      }

      // Otherwise exit menu.
      if (_menu != 0){
        _menu = 0;
        lcdPrint("IR", "HOME");
      }
      return;
    }

    if (k == "*"){
      // Start (or restart) token capture.
      commitTokenIfAny(robot);
      _capture = true;
      _token = "";
      _lastDigitMs = 0;
      emitEvent("token_start");
      if (_menu == 0) lcdPrint("MENU", "1..5");
      else lcdPrint(menuTop(), "VAL?");
      return;
    }

    if (k == "OK"){
      commitTokenIfAny(robot);
      _capture = false;
      _token = "";
      lcdPrint("TOKEN", "COMMIT");
      return;
    }

    if (isDigitKey(k)){
      // In menu mode, allow digits to start capture without needing '*'.
      if (!_capture){
        if (_menu == 0){
          // Home mode: digits just show KEY feedback (handled above).
          return;
        }
        _capture = true;
        _token = "";
      }
      _token += k;
      _lastDigitMs = millis();
      if (_menu == 0) lcdPrint("MENU:" + _token, "OK=SET");
      else lcdPrint("VAL:" + _token, "OK=SET");
      return;
    }
  }

  void tick(Robot &robot){
    if (!_capture) return;
    if (_token.length() == 0) return;
    if (_lastDigitMs == 0) return;
    if (millis() - _lastDigitMs >= (unsigned long)IR_TOKEN_TIMEOUT_MS){
      commitTokenIfAny(robot);
      _capture = false;
      _token = "";
    }
  }

private:
  static bool isDigitKey(const String &k){ return k.length() == 1 && k[0] >= '0' && k[0] <= '9'; }

  void commitTokenIfAny(Robot &robot){
    if (_token.length() == 0) return;
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
    // 5: Sound -> 1=loud, 2=quiet
    if (_menu == 0){
      _menu = (int)v;
      _servoSel = -1;
      emitMenu(_menu);
      lcdPrint(menuTop(), menuHint());
      return;
    }

    if (_menu == 1){
      if (!robot.servos.driverOk()){
        emitEvent("servo_driver_missing");
        lcdPrint("SERVO", "DRIVER MISSING");
        return;
      }
      if (_servoSel < 0){
        _servoSel = normalizeServoIndex(v);
        emitEvent("servo_sel", _servoSel);
        lcdPrint(menuTop(), "SERVO:" + String(_servoSel + 1) + " DEG?");
        return;
      }
      float deg = (float)constrain(v, 0, 180);
      robot.writeServoLimited(_servoSel, deg);
      emitEvent("servo_set", _servoSel, (long)deg);
      lcdPrint("SERVO:" + String(_servoSel + 1), "DEG:" + String((int)deg));
#if BUZZER_ENABLED
      g_buzzer.beepOn(g_buzzerDefaultOut, 2400, 40);
#endif
      return;
    }

    if (_menu == 2){
      robot.setDriveCmd((float)v);
      emitEvent("drive", v);
      lcdPrint("MENU:2 DRIVE", "SPEED:" + String((int)v));
      return;
    }

    if (_menu == 3){
#if LASER_ENABLED
      if (v == 1){ g_lasers.bothOn(); emitEvent("laser", 1); lcdPrint("MENU:3 LASER", "ON"); }
      else { g_lasers.off(); emitEvent("laser", 0); lcdPrint("MENU:3 LASER", "OFF"); }
#else
      emitEvent("laser_disabled");
      lcdPrint("MENU:3 LASER", "DISABLED");
#endif
      return;
    }

    if (_menu == 4){
      if (v == 1){ robot.setModeStand(); emitEvent("stand"); lcdPrint("MODE:STAND"); return; }
      if (v == 2){ robot.setModeSit(); emitEvent("sit"); lcdPrint("MODE:SIT"); return; }
      if (v == 3){ robot.setBalance(true); emitEvent("pid", 1); lcdPrint("MENU:4", "PID:ON"); return; }
      if (v == 4){ robot.setBalance(false); emitEvent("pid", 0); lcdPrint("MENU:4", "PID:OFF"); return; }
      emitEvent("mode_unknown", v);
      lcdPrint("MENU:4", "UNKNOWN");
      return;
    }

    if (_menu == 5){
#if BUZZER_ENABLED
      if (v == 1){
        g_buzzerDefaultOut = BUZZER_OUT_LOUD;
        g_song.setDefaultOut(g_buzzerDefaultOut);
        emitEvent("sound_out", 1);
        lcdPrint("MENU:5 SOUND", "LOUD");
        g_buzzer.beepOn(g_buzzerDefaultOut, 2200, 60);
        return;
      }
      if (v == 2){
        g_buzzerDefaultOut = BUZZER_OUT_QUIET;
        g_song.setDefaultOut(g_buzzerDefaultOut);
        emitEvent("sound_out", 2);
        lcdPrint("MENU:5 SOUND", "QUIET");
        g_buzzer.beepOn(g_buzzerDefaultOut, 2200, 60);
        return;
      }
#else
      emitEvent("sound_disabled");
      lcdPrint("MENU:5 SOUND", "DISABLED");
#endif
      return;
    }

    emitEvent("menu_unknown", _menu);
    lcdPrint("MENU:?", "UNKNOWN");
  }

#if LCD_ENABLED
  void lcdPrint(const String &top, const String &bottom = ""){
    if (_lcdPrint) _lcdPrint(top, bottom);
  }
  LcdPrintFn _lcdPrint{nullptr};
#else
  void lcdPrint(const String &, const String & = ""){ }
#endif

  String menuTop() const { return "MENU:" + String(_menu); }

  String menuHint() const {
    switch (_menu){
      case 1: return "SERVO then DEG";
      case 2: return "SPEED?";
      case 3: return "0=OFF 1=ON";
      case 4: return "1ST 2SI 3ON 4OFF";
      case 5: return "1LOUD 2QUIET";
      default: return "";
    }
  }

  static int normalizeServoIndex(long v){
    // Accept both 1-based (1..8) and 0-based (0..7)
    if (v >= 1 && v <= SERVO_COUNT_TOTAL) return (int)v - 1;
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

  int _menu{0};
  int _servoSel{-1};
  bool _capture{false};
  String _token;
  unsigned long _lastDigitMs{0};
};

#endif // IR_ENABLED

#endif // SENTRY_APP_IR_MENU_CONTROLLER_H
