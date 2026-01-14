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
    default: return "SOUND";
  }
}

void IrMenuController::showSound(){
#if BUZZER_ENABLED
  String out = (g_buzzerDefaultOut == BUZZER_OUT_LOUD) ? "LOUD" : "QUIET";
#else
  String out = "OFF";
#endif
  String line2 = soundName(_soundIndex) + " " + out;
  if ((SoundItem)_soundIndex == SOUND_MORSE) line2 += _morseMode ? " RUN" : " OK";
  lcdPrint("SOUND", line2);
}

void IrMenuController::playSelectedSound(){
#if BUZZER_ENABLED
  if ((SoundItem)_soundIndex == SOUND_WALLE){
    g_song.play("walle", g_buzzerDefaultOut);
    return;
  }
  if ((SoundItem)_soundIndex == SOUND_BB8){
    g_song.play("bb8", g_buzzerDefaultOut);
    return;
  }
  // MORSE is handled via _morseMode
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
  const uint16_t freq = 2200;
  const uint16_t dotMs = 80;
  const uint16_t dashMs = 240;
  const uint16_t gapMs = 80;
  const uint16_t longGapMs = 240;

  if (c == '.'){
    g_buzzer.beepOn(g_buzzerDefaultOut, freq, dotMs);
    _morseNextMs = now + (unsigned long)dotMs + (unsigned long)gapMs;
  } else if (c == '-'){
    g_buzzer.beepOn(g_buzzerDefaultOut, freq, dashMs);
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
