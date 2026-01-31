// SOUND implementations (moved into menus/ for organization)
#ifndef SENTRY_APP_IR_MENU_CONTROLLER_SOUND_H
#define SENTRY_APP_IR_MENU_CONTROLLER_SOUND_H

#if IR_ENABLED

#include "../xIrMenuController.h"

// SOUND / MORSE implementations moved out for readability

String IrMenuController::soundName(uint8_t idx){
  switch ((SoundItem)idx){
    case SOUND_WALLE: return "WALLE";
    case SOUND_BB8: return "BB8";
    case SOUND_MORSE: return "MORSE";
    case SOUND_BUZZER: return "BUZZER";
    case SOUND_BUZZER_SETTINGS: return "BUZZER SET";
    default: return "SOUND";
  }
}

void IrMenuController::showSound(){
  String buzzerState = (g_buzzerDefaultOut == BUZZER_OUT_LOUD) ? "LOUD" : "QUIET";
  String line2 = soundName(_soundIndex);
  if ((SoundItem)_soundIndex == SOUND_BUZZER){
    line2 += ": " + buzzerState;
    line2 += " L:" + String((int)g_buzzerFreqLoud);
    line2 += " Q:" + String((int)g_buzzerFreqQuiet);
    if (g_buzzerBothEnabled) line2 += " BOTH";
  } else {
    line2 += " " + buzzerState;
    if ((SoundItem)_soundIndex == SOUND_MORSE) line2 += _morseMode ? " RUN" : " OK";
  }
  if (_freqAdjustMode && _soundIndex == SOUND_BUZZER) line2 += " *=FREQ";
  if ((SoundItem)_soundIndex == SOUND_BUZZER_SETTINGS){
    // concise two-value display
    line2 = "L:" + String((int)g_buzzerFreqLoud) + " Q:" + String((int)g_buzzerFreqQuiet);
    if (g_buzzerBothEnabled) line2 += " BOTH";
  }
  lcdPrint("SOUND", line2);
}

void IrMenuController::playSelectedSound(){
#if BUZZER_ENABLED
  if ((SoundItem)_soundIndex == SOUND_WALLE){
    g_song.play("walle", g_buzzerDefaultOut);
    return;
  }
  if ((SoundItem)_soundIndex == SOUND_BB8){
    long r = random(0, 4);
    if (r == 0) g_song.play("bb8", g_buzzerDefaultOut);
    else if (r == 1) g_song.play("bb8_1", g_buzzerDefaultOut);
    else if (r == 2) g_song.play("bb8_2", g_buzzerDefaultOut);
    else g_song.play("bb8_3", g_buzzerDefaultOut);
    return;
  }
  if ((SoundItem)_soundIndex == SOUND_MORSE){
    _morseMode = !_morseMode;
    if (_morseMode) lcdPrint("MORSE", "KEY=CODE #=BK");
    return;
  }
  if ((SoundItem)_soundIndex == SOUND_BUZZER){
    g_buzzerDefaultOut = (g_buzzerDefaultOut == BUZZER_OUT_LOUD) ? BUZZER_OUT_QUIET : BUZZER_OUT_LOUD;
    g_song.setDefaultOut(g_buzzerDefaultOut);
    if (g_buzzerBothEnabled){
      g_buzzer.beepOn(BUZZER_OUT_LOUD, g_buzzerFreqLoud, 50);
      g_buzzer.beepOn(BUZZER_OUT_QUIET, g_buzzerFreqQuiet, 50);
    } else {
      uint16_t f = (g_buzzerDefaultOut==BUZZER_OUT_LOUD)?g_buzzerFreqLoud:g_buzzerFreqQuiet;
      g_buzzer.beepOn(g_buzzerDefaultOut, f, 50);
    }
    return;
  }
  if ((SoundItem)_soundIndex == SOUND_BUZZER_SETTINGS){
    // Enter buzzer settings state
    _state = STATE_SOUND; // keep STATE_SOUND but show settings
    _soundIndex = SOUND_BUZZER_SETTINGS;
    showSound();
    return;
  }
#endif
}

String IrMenuController::morsePatternForKey(const String &k){
  // Digits 0-9
  if (k == "0") return "-----";
  if (k == "1") return ".----";
  if (k == "2") return "..---";
  if (k == "3") return "...--";
  if (k == "4") return "....-";
  if (k == "5") return ".....";
  if (k == "6") return "-....";
  if (k == "7") return "--...";
  if (k == "8") return "---..";
  if (k == "9") return "----.";

  // A few handy tests
  if (k == "OK") return "...---..."; // SOS
  if (k == "UP") return "..-";
  if (k == "DOWN") return "-..";
  if (k == "LEFT") return ".-..";
  if (k == "RIGHT") return ".-.";
  if (k == "*") return "...-";
  if (k == "#") return "....";
  return "";
}

void IrMenuController::startMorse(const String &pattern){
#if BUZZER_ENABLED
  _morsePattern = pattern;
  _morseIdx = 0;
  _morsePlaying = true;
  _morseNextMs = 0;
#endif
}

void IrMenuController::tickMorse(){
#if BUZZER_ENABLED
  if (!_morsePlaying) return;
  unsigned long now = millis();
  if (_morseNextMs != 0 && (long)(now - _morseNextMs) < 0) return;

  if (_morseIdx >= (uint16_t)_morsePattern.length()){
    _morsePlaying = false;
    _morseNextMs = 0;
    return;
  }

  const char c = _morsePattern[_morseIdx++];
  const uint16_t freq = (g_buzzerDefaultOut==BUZZER_OUT_LOUD)?g_buzzerFreqLoud:g_buzzerFreqQuiet;
  const uint16_t dotMs = 80;
  const uint16_t dashMs = 240;
  const uint16_t gapMs = 80;
  const uint16_t longGapMs = 240;

  if (c == '.'){
    if (g_buzzerBothEnabled){
      g_buzzer.beepOn(BUZZER_OUT_LOUD, g_buzzerFreqLoud, dotMs);
      g_buzzer.beepOn(BUZZER_OUT_QUIET, g_buzzerFreqQuiet, dotMs);
    } else g_buzzer.beepOn(BUZZER_OUT_LOUD, freq, dotMs);
    _morseNextMs = now + (unsigned long)dotMs + (unsigned long)gapMs;
  } else if (c == '-'){
    if (g_buzzerBothEnabled){
      g_buzzer.beepOn(BUZZER_OUT_LOUD, g_buzzerFreqLoud, dashMs);
      g_buzzer.beepOn(BUZZER_OUT_QUIET, g_buzzerFreqQuiet, dashMs);
    } else g_buzzer.beepOn(BUZZER_OUT_LOUD, freq, dashMs);
    _morseNextMs = now + (unsigned long)dashMs + (unsigned long)gapMs;
  } else {
    _morseNextMs = now + (unsigned long)longGapMs;
  }
#endif
}

String IrMenuController::textToMorse(const String &text){
  // Basic A-Z 0-9 mapping; unknown chars produce word gap
  static const char *map[36] = {
    ".-","-...","-.-.","-..",".","..-.","--.","....","..",
    ".---","-.-",".-..","--","-.","---",".--.","--.-",".-.",
    "...","-","..-","...-",".--","-..-","-.--","--..",
    "-----",".----","..---","...--","....-",".....","-....","--...","---..","----."
  };
  String out = "";
  for (int i=0;i<text.length();i++){
    char c = text[i];
    if (c >= 'a' && c <= 'z') c = c - 'a' + 'A';
    if (c >= 'A' && c <= 'Z'){
      out += String(map[c - 'A']);
      out += ' '; // letter gap
    } else if (c >= '0' && c <= '9'){
      out += String(map[26 + (c - '0')]);
      out += ' ';
    } else if (c == ' '){
      out += '/'; // word gap marker -> treated as long gap by tickMorse
    } else {
      out += '/';
    }
  }
  return out;
}

#endif // IR_ENABLED

#endif // SENTRY_APP_IR_MENU_CONTROLLER_SOUND_H
