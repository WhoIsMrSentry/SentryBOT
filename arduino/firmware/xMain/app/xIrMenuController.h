#ifndef SENTRY_APP_IR_MENU_CONTROLLER_H
#define SENTRY_APP_IR_MENU_CONTROLLER_H

#include <Arduino.h>
#include <EEPROM.h>
#include "../xConfig.h"
#include "../xRobot.h"
#include "../peripherals/xEbyteRadio.h"
#include "../actuators/xNemaController.h"
#include "xCuteBuzzer.h"

// Asynchronous hall calibration helper implemented in xMain.ino
void startEncoderCalibration(unsigned long durMs, bool updateLcd);

#if VIRTUAL_MENU_ENABLED

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

#if HALL_ENCODER_ENABLED
#include "../peripherals/xHallEncoder.h"
extern HallEncoder g_hall0;
extern HallEncoder g_hall1;
#endif

#if LCD_ENABLED
extern bool g_lcd1Ok;
#endif

#if DS18_ENABLED
#include "../peripherals/xDs18b20.h"
#endif

extern EbyteRadio g_ebyteRadio;

class IrMenuController {
public:
  void reset(){
    _state = STATE_HOME;
    _menuIndex = 1; // Default to first sub-menu item (Servo) instead of Home to avoid easy loops
    _token = "";
    _capture = false;
    _lastDigitMs = 0;
    _lastInputMs = millis();
    _servoSel = -1;
    _laserMode = 0;
    _lastUiMs = 0;
    _imuSub = 0;

    _soundIndex = 0;
    _morseMode = false;
    _morsePattern = "";
    _morseIdx = 0;
    _morseNextMs = 0;
    _morsePlaying = false;
    _lastProxBeepMs = 0;
#if LCD_ENABLED
    g_lcdStatus.setPinned(false);
#endif
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
    if (g_buzzerBothEnabled){
      g_buzzer.beepBoth(g_buzzerFreqLoud, 30);
    } else {
      uint16_t f = (g_buzzerDefaultOut == BUZZER_OUT_LOUD) ? g_buzzerFreqLoud : g_buzzerFreqQuiet;
      g_buzzer.beepOn(g_buzzerDefaultOut, f, 30);
    }
#endif

    // Global back/cancel (hierarchical navigation)
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
      if (_state == STATE_MENU){
        enterHome();
        return;
      }
      if (_state != STATE_HOME){
        _state = STATE_MENU;
        showMenu();
        return;
      }
      // already home
      showHome();
      return;
    }

    // Global Home key (*) — handle BEFORE the home-state block so that
    // pressing HOME from the website while already at home refreshes the
    // screen instead of falling through to the unknown-key path.
    if (k == "*"){
      enterHome();
      _lastInputMs = millis();
      return;
    }

    // HOME: keep simple direct controls; OK opens menu
    if (_state == STATE_HOME){
      if (k == "OK"){
        _lastInputMs = millis(); 
        enterMenu();
        return;
      }
      // Replace stand/sit animations with position-based stepper moves
      if (k == "LEFT"){
        // Steering left: move both tracks forward but inner (left) wheel fewer steps
        float revs_per_deg = STEPPER_STEPS_PER_REV / 360.0f;
        long outer_steps = (long)(STEERING_FORWARD_DEG * revs_per_deg);
        long inner_steps = (long)(outer_steps * STEERING_INNER_SCALE);
        // both forward, left inner slower (ramped)
        robot.steppers.startRampedDrive(0, 1, 20000UL, 800UL, 0.995f, inner_steps);
        robot.steppers.startRampedDrive(1, 1, 20000UL, 800UL, 0.995f, outer_steps);
        lcdPrint("TURN", "LEFT"); emitEvent("steer", -1);
        return;
      }
      if (k == "RIGHT"){
        float revs_per_deg = STEPPER_STEPS_PER_REV / 360.0f;
        long outer_steps = (long)(STEERING_FORWARD_DEG * revs_per_deg);
        long inner_steps = (long)(outer_steps * STEERING_INNER_SCALE);
        // both forward, right inner slower (ramped)
        robot.steppers.startRampedDrive(0, 1, 20000UL, 800UL, 0.995f, outer_steps);
        robot.steppers.startRampedDrive(1, 1, 20000UL, 800UL, 0.995f, inner_steps);
        lcdPrint("TURN", "RIGHT"); emitEvent("steer", 1);
        return;
      }
      if (k == "DOWN"){
        // Move backward a short distance
        float revs_per_deg = STEPPER_STEPS_PER_REV / 360.0f;
        long steps = (long)(STEERING_FORWARD_DEG * revs_per_deg);
        robot.steppers.startRampedDrive(0, -1, 20000UL, 800UL, 0.995f, steps);
        robot.steppers.startRampedDrive(1, -1, 20000UL, 800UL, 0.995f, steps);
        lcdPrint("DRIVE", "BACK"); emitEvent("drive", -100);
        return;
      }
      if (k == "UP"){
        // Move forward a short distance
        float revs_per_deg = STEPPER_STEPS_PER_REV / 360.0f;
        long steps = (long)(STEERING_FORWARD_DEG * revs_per_deg);
        robot.steppers.startRampedDrive(0, 1, 20000UL, 800UL, 0.995f, steps);
        robot.steppers.startRampedDrive(1, 1, 20000UL, 800UL, 0.995f, steps);
        lcdPrint("DRIVE", "FORWARD"); emitEvent("drive", 100);
        return;
      }
      // Unknown/digit keys at home: silently re-render home so the screen
      // never gets replaced by debug "IR KEY:" overlays.
      showHome();
      return;
    }

    // Global Back key handler from textual aliases
    if (k == "BACK"){
      if (_state == STATE_MENU){
        _state = STATE_HOME;
        showHome();
      } else if (_state != STATE_HOME){
        _state = STATE_MENU;
        showMenu();
      }
      _lastInputMs = millis();
      return;
    }
    
    // reset activity on any other key
    _lastInputMs = millis();

    // MENU: UP/DOWN select, OK enter
    if (_state == STATE_MENU){
      if (k == "UP"){ menuPrev(); return; }
      if (k == "DOWN"){ menuNext(); return; }
      if (k == "OK"){ enterSelected(robot); return; }
      // ignore others
      return;
    }

    // Servo flow
    if (_state == STATE_SERVO_SEL || _state == STATE_SERVO_DEG){
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

      // '*' enters freq-adjust mode (or numeric capture when already adjusting)
      if (k == "*" && (_soundIndex == SOUND_BUZZER || _soundIndex == SOUND_BUZZER_SETTINGS)){
        if (!_freqAdjustMode){
          _freqAdjustMode = true;
          _buzzerNumCapture = false;
          _buzzerNumToken = "";
          showSound();
        } else if (!_buzzerNumCapture){
          _buzzerNumCapture = true;
          _buzzerNumToken = "";
          lcdPrint(F("ENTER NUM"), F("(OK=SAVE)"));
        } else {
          _buzzerNumCapture = false;
          _buzzerNumToken = "";
          showSound();
        }
        return;
      }

      // If in freq-adjust mode, handle numeric capture, UP/DOWN step, and '#' save-and-exit
      if (_freqAdjustMode){
        if (k == "#"){
#if BUZZER_ENABLED
          EEPROM.put(EEPROM_ADDR_BUZZER_FREQ_LOUD, g_buzzerFreqLoud);
          EEPROM.put(EEPROM_ADDR_BUZZER_FREQ_QUIET, g_buzzerFreqQuiet);
          EEPROM.update(EEPROM_ADDR_BUZZER_FREQ_MAGIC, EEPROM_BUZZER_MAGIC);
#endif
          _freqAdjustMode = false;
          _buzzerNumCapture = false;
          _buzzerNumToken = "";
          lcdPrint(F("SOUND"), F("FREQ SAVED"));
          return;
        }

        if (_buzzerNumCapture){
          if (isDigitKey(k)){
            if (_buzzerNumToken.length() < 4) _buzzerNumToken += k;
            lcdPrint(String(F("NUM:")), _buzzerNumToken);
          } else if (k == "OK"){
            long v = _buzzerNumToken.toInt();
            if (v >= 200 && v <= 4000){
              if (_buzzerSel == SEL_BUZZER_LOUD) g_buzzerFreqLoud = (uint16_t)v;
              else g_buzzerFreqQuiet = (uint16_t)v;
            }
            _buzzerNumCapture = false;
            _buzzerNumToken = "";
            showSound();
          }
          return;
        }

        int sel = (_buzzerSel == SEL_BUZZER_QUIET) ? SEL_BUZZER_QUIET : SEL_BUZZER_LOUD;
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
            g_buzzer.beepBoth(g_buzzerFreqLoud, 80);
          } else {
            uint16_t f = (g_buzzerDefaultOut == BUZZER_OUT_LOUD) ? g_buzzerFreqLoud : g_buzzerFreqQuiet;
            g_buzzer.beepOn(g_buzzerDefaultOut, f, 80);
          }
#endif
        }
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

      // Morse mode: digits (and OK) produce deterministic patterns.
      if (_morseMode){
        String pat = morsePatternForKey(k);
        if (pat.length() > 0){
          startMorse(pat);
          lcdPrint(String(F("MORSE:")) + k, pat);
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
  }

  void tick(Robot &robot){
    // Manual Home is now via '*' key. Auto-Home removed upon user request.
    
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
          g_buzzer.beepBoth(g_buzzerFreqLoud, 30);
        } else {
          g_buzzer.beepOn(BUZZER_OUT_LOUD, g_buzzerFreqLoud, 30);
        }
      }
    }
#endif

    // Periodic refresh for live sensor pages (ULTRA/IMU/RFID/SYSTEM)
    unsigned long _now = millis();
    if (_state == STATE_ULTRA || _state == STATE_IMU || _state == STATE_RFID || _state == STATE_SYSTEM || _state == STATE_TEMPS){
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
    STATE_TEMPS,
    STATE_ALERTS,
    STATE_STATS,
  };

  enum MenuItem : uint8_t {
    MENU_HOME = 0,
    MENU_SERVO,
    MENU_LASER,
    MENU_ULTRA,
    MENU_IMU,
    MENU_RFID,
    MENU_SOUND,
    MENU_CALIBRATE,
    MENU_SYSTEM,
    MENU_TEMPS,
    MENU_ALERTS,
    MENU_STATS,
    MENU_COUNT,
  };

  enum SoundItem : uint8_t {
    SOUND_WALLE = 0,
    SOUND_BB8,
    SOUND_CUTE_CONNECTION,
    SOUND_CUTE_DISCONNECT,
    SOUND_CUTE_BUTTON,
    SOUND_CUTE_MODE1,
    SOUND_CUTE_MODE2,
    SOUND_CUTE_MODE3,
    SOUND_CUTE_HAPPY,
    SOUND_CUTE_HAPPY_SHORT,
    SOUND_CUTE_SUPER_HAPPY,
    SOUND_CUTE_SAD,
    SOUND_CUTE_SURPRISE,
    SOUND_CUTE_OHOOH,
    SOUND_CUTE_OHOOH2,
    SOUND_CUTE_CUDDLY,
    SOUND_CUTE_CONFUSED,
    SOUND_CUTE_SLEEPING,
    SOUND_CUTE_FART1,
    SOUND_CUTE_FART2,
    SOUND_CUTE_FART3,
    SOUND_CUTE_JUMP,
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
    // Home screen is the idle screen; allow background status overlays here.
    g_lcdStatus.setPinned(false);
    g_lcdStatus.invalidate();
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
    g_lcdStatus.invalidate();
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
    updateScroll();
    showMenu();
  }
  void menuNext(){
    _menuIndex = (_menuIndex + 1) % MENU_COUNT;
    updateScroll();
    showMenu();
  }

  void updateScroll(){
    if (_menuIndex < _menuScroll){
      _menuScroll = _menuIndex;
    } else if (_menuIndex >= _menuScroll + 4){
      _menuScroll = _menuIndex - 3;
    }
  }

  static const __FlashStringHelper* menuName(uint8_t idx){
    switch ((MenuItem)idx){
      case MENU_HOME: return (const __FlashStringHelper*)F("HOME");
      case MENU_SERVO: return (const __FlashStringHelper*)F("SERVO");
      case MENU_LASER: return (const __FlashStringHelper*)F("LASER");
      case MENU_ULTRA: return (const __FlashStringHelper*)F("ULTRA");
      case MENU_IMU: return (const __FlashStringHelper*)F("IMU");
      case MENU_RFID: return (const __FlashStringHelper*)F("RFID");
      case MENU_SOUND: return (const __FlashStringHelper*)F("SOUND");
      case MENU_TEMPS: return (const __FlashStringHelper*)F("TEMPS");
      case MENU_CALIBRATE: return (const __FlashStringHelper*)F("CALIBRATION");
      case MENU_SYSTEM: return (const __FlashStringHelper*)F("SYSTEM INFO");
      case MENU_ALERTS: return (const __FlashStringHelper*)F("ALERT HISTORY");
      case MENU_STATS: return (const __FlashStringHelper*)F("ROBOT STATS");
      default: return (const __FlashStringHelper*)F("MENU");
    }
  }

  void showHome(){
    // Plain ASCII rows so that no part of the home screen depends on CGRAM
    // custom characters being intact (which is fragile across menu repaints).
    lcdHubShow4(
      F("   SentryBOT  V7    "),
      F("===================="),
      F("  STATUS: ONLINE    "),
      F(" [OK] OPEN MENU     ")
    );
  }

  void showMenu(){
    String rows[4];
    for (int i=0; i<4; i++){
      int idx = _menuScroll + i;
      if (idx < MENU_COUNT){
        // Use custom arrow icon (0) for selection
        rows[i] = (idx == _menuIndex) ? F("\x00 ") : F("  ");
        rows[i] += menuName(idx);
      } else {
        rows[i] = "";
      }
    }
    lcdHubShow4(rows[0], rows[1], rows[2], rows[3]);
  }

  // Render one temperature cell: "<icon><Name>:<value>C" without %f (unsupported in AVR libc by default).
  static void formatTempCell(char *out, size_t outSz, const char *name, float t){
    if (isnan(t)){
      snprintf_P(out, outSz, PSTR("\x01" "%s:--.-C"), name);
      return;
    }
    char num[10];
    dtostrf(t, 4, 1, num);
    char *p = num;
    while (*p == ' ') p++;
    snprintf_P(out, outSz, PSTR("\x01" "%s:%sC"), name, p);
  }

  void showTemperatures(){
#if DS18_ENABLED
    String rows[4];
    for (int r=0;r<4;r++){
      uint8_t leftIdx = 4 + r;
      uint8_t rightIdx = r;
      const char *leftName = g_ds18.name(leftIdx);
      const char *rightName = g_ds18.name(rightIdx);
      float lt = g_ds18.tempC(leftIdx);
      float rt = g_ds18.tempC(rightIdx);
      char lb[16]; char rb[16];
      formatTempCell(lb, sizeof(lb), leftName, lt);
      formatTempCell(rb, sizeof(rb), rightName, rt);
      String leftStr(lb); String rightStr(rb);
      if ((int)leftStr.length() > 10) leftStr = leftStr.substring(0,10);
      if ((int)rightStr.length() > 10) rightStr = rightStr.substring(0,10);
      while ((int)leftStr.length() < 10) leftStr += ' ';
      if ((int)rightStr.length() < 10){
        String pad = "";
        for (int p=0; p < 10 - (int)rightStr.length(); p++) pad += ' ';
        rightStr = pad + rightStr;
      }
      rows[r] = leftStr + rightStr;
    }
    lcdHubShow4(rows[0], rows[1], rows[2], rows[3]);
#else
    lcdPrint(F("TEMPS"), F("DISABLED"));
#endif
  }

  void enterSelected(Robot &robot){
#if LCD_ENABLED
    // Each new state should start with a clean LCD so static menus do not
    // inherit half-rendered content from previous screens.
    g_lcdStatus.invalidate();
#endif
    switch ((MenuItem)_menuIndex){
      case MENU_HOME:
        _state = STATE_HOME;
        showHome();
        return;

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

      case MENU_TEMPS:
        _state = STATE_TEMPS;
        _lastUiMs = 0;
        // Force a fresh DS18 read on entry so the menu shows live values
        // immediately rather than NaNs / last cached cycle.
#if DS18_ENABLED
        g_ds18.forceRead();
#endif
        showTemperatures();
        return;

      case MENU_CALIBRATE:
#if HALL_ENCODER_ENABLED
        _state = STATE_SYSTEM;
        startEncoderCalibration(5000UL, true);
        return;
#else
        lcdPrint(F("CAL"), F("HALL DISABLED"));
        return;
#endif

      case MENU_SYSTEM:
        _state = STATE_SYSTEM;
        _lastUiMs = 0;
        refreshLive(robot);
        return;

      case MENU_ALERTS:
        _state = STATE_ALERTS;
        _lastUiMs = 0;
        showAlerts();
        return;

      case MENU_STATS:
        _state = STATE_STATS;
        _lastUiMs = 0;
        showStats();
        return;

      default:
        return;
    }
  }

  void showServoPrompt();
  void showServoToken();

  void showLaser(){
    char l1[21], l2[21], l3[21], l4[21];
    const char* const modes[] = {"  ALL OFF   ", " LASER 1 ON ", " LASER 2 ON ", " BOTH ON    "};
    snprintf_P(l1, sizeof(l1), PSTR("   LASER CONTROL    "));
    snprintf_P(l2, sizeof(l2), PSTR("--------------------"));
    snprintf_P(l3, sizeof(l3), PSTR("  MODE: %-12s"), modes[_laserMode % 4]);
    snprintf_P(l4, sizeof(l4), PSTR(" [UP/DN]=CHG [OK]=SET"));
    lcdHubShow4(l1, l2, l3, l4);
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
      char top[16]; char bottom[16];
      snprintf_P(top, sizeof(top), PSTR("SERVO:%d"), _servoSel + 1);
      snprintf_P(bottom, sizeof(bottom), PSTR("DEG:%d"), (int)deg);
      lcdPrint(String(top), String(bottom));
#if BUZZER_ENABLED
      if (g_buzzerBothEnabled){
        g_buzzer.beepBoth(g_buzzerFreqLoud, 40);
      } else {
        g_buzzer.beepOn(g_buzzerDefaultOut, (g_buzzerDefaultOut == BUZZER_OUT_LOUD) ? g_buzzerFreqLoud : g_buzzerFreqQuiet, 40);
      }
#endif
      return;
    }
  }

  void addAlert(const String &msg){
    if (msg == _alerts[0]) return; // Simple deduplication
    for (int i=2; i>=0; i--) strncpy(_alerts[i+1], _alerts[i], 21);
    strncpy(_alerts[0], msg.c_str(), 21);
    _alerts[0][20] = '\0';
  }

  void showAlerts(){
    char l1[21];
    snprintf_P(l1, sizeof(l1), PSTR("   ALERT HISTORY    "));
    lcdHubShow4(String(l1), String(_alerts[0]), String(_alerts[1]), String(_alerts[2]));
  }

  void showStats(){
    char l1[21], l2[21], l3[21], l4[21];
    snprintf_P(l1, sizeof(l1), PSTR("    SENTRY STATS    "));
    snprintf_P(l2, sizeof(l2), PSTR("--------------------"));
#if HALL_ENCODER_ENABLED
    snprintf_P(l3, sizeof(l3), PSTR("H0:%lu H1:%lu       "), g_hall0.getCount(), g_hall1.getCount());
#else
    snprintf_P(l3, sizeof(l3), PSTR("HALL: DISABLED      "));
#endif
    // Rough loops per second
    unsigned long now = millis();
    unsigned long elapsed = now - _lastStatMs;
    if (elapsed > 1000){
      _lastLps = (_loopCount * 1000) / elapsed;
      _loopCount = 0;
      _lastStatMs = now;
    }
    snprintf_P(l4, sizeof(l4), PSTR("PERF: %lu LPS       "), _lastLps);
    lcdHubShow4(l1, l2, l3, l4);
  }

  void countLoop() { _loopCount++; }

  static void lcdHubShow4(const String &l1, const String &l2, const String &l3, const String &l4){
#if LCD_ENABLED
    g_lcdStatus.show4To(LCD_TGT_1, l1, l2, l3, l4, true);
#else
    (void)l1; (void)l2; (void)l3; (void)l4;
#endif
  }
  static void lcdHubShow4(const __FlashStringHelper *l1, const __FlashStringHelper *l2, const __FlashStringHelper *l3, const __FlashStringHelper *l4){
#if LCD_ENABLED
    g_lcdStatus.show4To(LCD_TGT_1, l1, l2, l3, l4, true);
#else
    (void)l1; (void)l2; (void)l3; (void)l4;
#endif
  }

#if LCD_ENABLED
  void lcdPrint(const String &top, const String &bottom = ""){
    if (LCD_ROWS >= 4) g_lcdStatus.show4To(LCD_TGT_1, top, bottom, "", "", true);
    else if (_lcdPrint) _lcdPrint(top, bottom);
  }
  void lcdPrint(const __FlashStringHelper* top, const __FlashStringHelper* bottom = NULL){
    if (LCD_ROWS >= 4) g_lcdStatus.show4To(LCD_TGT_1, top, bottom, (const __FlashStringHelper*)F(""), (const __FlashStringHelper*)F(""), true);
    else if (_lcdPrint) _lcdPrint(String(top), bottom ? String(bottom) : "");
  }
  LcdPrintFn _lcdPrint{nullptr};
#else
  void lcdPrint(const String &, const String & = ""){ }
  void lcdPrint(const __FlashStringHelper *, const __FlashStringHelper * = nullptr){ }
#endif

  void refreshLive(Robot &robot);

  // Public helper for direct menu navigation from web UI / commands
  void gotoHome(){
    enterHome();
    _menuIndex = 1;
  }

  void gotoMenu(MenuItem menu, Robot &robot){
    if (menu == MENU_HOME){
      gotoHome();
      return;
    }
#if LCD_ENABLED
    // Web-based direct menu jumps should behave like interactive menu mode.
    g_lcdStatus.setPinned(true);
    g_lcdStatus.invalidate();
#endif
    _menuIndex = (uint8_t)menu;
    enterSelected(robot);
  }

private:

  static int normalizeServoIndex(long v){
    // Accept both 1-based (1..N) and 0-based (0..N-1) inputs from users
    if (v >= 1 && v <= SERVO_COUNT_TOTAL) return (int)(v - 1);
    return (int)constrain(v, 0, SERVO_COUNT_TOTAL - 1);
  }

  static void emitEvent(const char *name, long v){
    SERIAL_IO.print(F("{\"ok\":true,\"event\":\"ir\",\"name\":\""));
    SERIAL_IO.print(name);
    SERIAL_IO.print(F("\",\"v\":"));
    SERIAL_IO.print(v);
    SERIAL_IO.println('}');
  }

  static void emitEvent(const char *name, long a, long b){
    SERIAL_IO.print(F("{\"ok\":true,\"event\":\"ir\",\"name\":\""));
    SERIAL_IO.print(name);
    SERIAL_IO.print(F("\",\"a\":"));
    SERIAL_IO.print(a);
    SERIAL_IO.print(F(",\"b\":"));
    SERIAL_IO.print(b);
    SERIAL_IO.println('}');
  }

  State _state{STATE_HOME};
  uint8_t _menuIndex{0};
  uint8_t _menuScroll{0};

  int _servoSel{-1};
  uint8_t _laserMode{0}; // 0:OFF, 1:L1, 2:L2, 3:BOTH

  bool _capture{false};
  String _token;
  unsigned long _lastDigitMs{0};

  unsigned long _lastUiMs{0};
  uint8_t _imuSub{0};

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

  unsigned long _lastProxBeepMs{0};
  char _alerts[4][21] = {"NONE", "NONE", "NONE", "NONE"};
  uint32_t _loopCount{0};
  uint32_t _lastLps{0};
  unsigned long _lastStatMs{0};
  unsigned long _lastInputMs{0};
};

#include "menus/xIrMenuController_sound.h"
#include "menus/xIrMenuController_servo.h"
#include "menus/xIrMenuController_sensors.h"

#endif // VIRTUAL_MENU_ENABLED

#endif // SENTRY_APP_IR_MENU_CONTROLLER_H
