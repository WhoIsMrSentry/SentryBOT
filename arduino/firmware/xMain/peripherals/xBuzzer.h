#ifndef SENTRY_PERIPHERALS_BUZZER_H
#define SENTRY_PERIPHERALS_BUZZER_H

#include <Arduino.h>
#include "../xConfig.h"

#if BUZZER_ENABLED
#include <avr/pgmspace.h>

#if IR_ENABLED
// Only needed for the optional IR re-init fail-safe when using tone().
#include <IRremote.hpp>
#endif

enum BuzzerOut : uint8_t {
  BUZZER_OUT_LOUD = 0,
  BUZZER_OUT_QUIET = 1,
};

class BuzzerPair {
public:
  void begin(uint8_t loudPin, uint8_t quietPin){
    _loud = loudPin;
    _quiet = quietPin;
    pinMode(_loud, OUTPUT);
    pinMode(_quiet, OUTPUT);
    stop();
  }

  void update(){
#if !(BUZZER_USE_TONE && !(IR_ENABLED && BUZZER_DISABLE_TONE_WHEN_IR))
    if (_activePin != 255){
      unsigned long now = millis();
      // millis() overflow safe compare
      if ((long)(now - _activeUntilMs) >= 0){
        digitalWrite(_activePin, LOW);
        _activePin = 255;
        _activeUntilMs = 0;
      }
    }
#endif

#if IR_ENABLED && BUZZER_USE_TONE && BUZZER_REINIT_IR_AFTER_TONE
    if (_irReinitAtMs != 0){
      unsigned long now2 = millis();
      if ((long)(now2 - _irReinitAtMs) >= 0){
        IrReceiver.begin(IR_PIN, ENABLE_LED_FEEDBACK);
        _irReinitAtMs = 0;
      }
    }
#endif
  }

  void beepOn(BuzzerOut out, uint16_t freqHz = 2200, uint16_t ms = 60){
    uint8_t pin = selectPin(out);
    if (pin == 255) return;

#if BUZZER_USE_TONE && !(IR_ENABLED && BUZZER_DISABLE_TONE_WHEN_IR)
    tone(pin, freqHz, ms);

#if IR_ENABLED && BUZZER_REINIT_IR_AFTER_TONE
    // tone() may disturb IRremote timers on AVR; re-init IR after the tone ends.
    unsigned long target = millis() + (unsigned long)ms + 5UL;
    if (_irReinitAtMs == 0 || (long)(target - _irReinitAtMs) > 0){
      _irReinitAtMs = target;
    }
#endif
#else
    // Non-blocking beep (no delay). Frequency is ignored in this mode.
    // If another beep is active, override it.
    if (_activePin != 255 && _activePin != pin){
      digitalWrite(_activePin, LOW);
    }
    digitalWrite(pin, HIGH);
    _activePin = pin;
    _activeUntilMs = millis() + (unsigned long)ms;
#endif
  }

  void stop(){
#if BUZZER_USE_TONE && !(IR_ENABLED && BUZZER_DISABLE_TONE_WHEN_IR)
    if (_loud != 255) noTone(_loud);
    if (_quiet != 255) noTone(_quiet);
#endif
    if (_loud != 255) digitalWrite(_loud, LOW);
    if (_quiet != 255) digitalWrite(_quiet, LOW);

#if !(BUZZER_USE_TONE && !(IR_ENABLED && BUZZER_DISABLE_TONE_WHEN_IR))
    _activePin = 255;
    _activeUntilMs = 0;
#endif

#if IR_ENABLED && BUZZER_USE_TONE && BUZZER_REINIT_IR_AFTER_TONE
    _irReinitAtMs = 0;
#endif
  }

private:
  uint8_t selectPin(BuzzerOut out) const {
    return (out == BUZZER_OUT_LOUD) ? _loud : _quiet;
  }

  uint8_t _loud{255};
  uint8_t _quiet{255};

#if !(BUZZER_USE_TONE && !(IR_ENABLED && BUZZER_DISABLE_TONE_WHEN_IR))
  uint8_t _activePin{255};
  unsigned long _activeUntilMs{0};
#endif

#if IR_ENABLED && BUZZER_USE_TONE && BUZZER_REINIT_IR_AFTER_TONE
  unsigned long _irReinitAtMs{0};
#endif
};

struct BuzzerNote {
  uint16_t freq;
  uint16_t durMs;
  uint16_t gapMs;
};

class BuzzerSongPlayer {
public:
  void begin(BuzzerPair *pair){
    _pair = pair;
    stop();
  }

  void setDefaultOut(BuzzerOut out){ _defaultOut = out; }
  BuzzerOut defaultOut() const { return _defaultOut; }

  void play(const String &name, BuzzerOut out){
    const BuzzerNote *song = nullptr;
    uint8_t len = 0;
    if (!resolveSong(name, song, len)) return;

    _song = song;
    _len = len;
    _idx = 0;
    _out = out;
    _state = PLAYING;
    _nextMs = 0;
  }

  void playDefault(const String &name){ play(name, _defaultOut); }

  void stop(){
    _state = IDLE;
    _song = nullptr;
    _len = 0;
    _idx = 0;
    _nextMs = 0;
  }

  void update(){
    if (_state == IDLE || !_pair || !_song || _len == 0) return;

    unsigned long now = millis();
    if (_nextMs != 0 && now < _nextMs) return;

    if (_idx >= _len){
      stop();
      return;
    }

    BuzzerNote n;
    n.freq = pgm_read_word(&_song[_idx].freq);
    n.durMs = pgm_read_word(&_song[_idx].durMs);
    n.gapMs = pgm_read_word(&_song[_idx].gapMs);

    if (n.freq > 0 && n.durMs > 0){
      _pair->beepOn(_out, n.freq, n.durMs);
      _nextMs = now + (unsigned long)n.durMs + (unsigned long)n.gapMs;
    } else {
      _nextMs = now + (unsigned long)n.gapMs;
    }
    _idx++;
  }

private:
  enum State : uint8_t { IDLE = 0, PLAYING = 1 };

  static bool resolveSong(const String &name, const BuzzerNote *&outSong, uint8_t &outLen);

  // Minimal melodies: short and distinctive (passive buzzer).
  static const BuzzerNote SONG_WALLE[] PROGMEM;
  static const BuzzerNote SONG_BB8[] PROGMEM;

  BuzzerPair *_pair{nullptr};
  const BuzzerNote *_song{nullptr};
  uint8_t _len{0};
  uint8_t _idx{0};
  unsigned long _nextMs{0};
  BuzzerOut _defaultOut{BUZZER_OUT_QUIET};
  BuzzerOut _out{BUZZER_OUT_QUIET};
  State _state{IDLE};
};

// Definitions
const BuzzerNote BuzzerSongPlayer::SONG_WALLE[] PROGMEM = {
  {880, 80, 30}, {0, 0, 40}, {1319, 120, 50}, {988, 90, 80}, {1175, 140, 60},
  {0, 0, 70}, {784, 120, 40}, {988, 160, 100},
};

const BuzzerNote BuzzerSongPlayer::SONG_BB8[] PROGMEM = {
  {1760, 40, 20}, {1976, 40, 20}, {2093, 50, 30}, {0, 0, 40},
  {1568, 70, 30}, {2093, 60, 40}, {0, 0, 60}, {2349, 80, 120},
};

inline bool BuzzerSongPlayer::resolveSong(const String &name, const BuzzerNote *&outSong, uint8_t &outLen){
  if (name.equalsIgnoreCase("walle") || name.equalsIgnoreCase("wall-e")){
    outSong = SONG_WALLE;
    outLen = (uint8_t)(sizeof(SONG_WALLE) / sizeof(SONG_WALLE[0]));
    return true;
  }
  if (name.equalsIgnoreCase("bb8") || name.equalsIgnoreCase("bb-8")){
    outSong = SONG_BB8;
    outLen = (uint8_t)(sizeof(SONG_BB8) / sizeof(SONG_BB8[0]));
    return true;
  }
  return false;
}

#endif // BUZZER_ENABLED

#endif // SENTRY_PERIPHERALS_BUZZER_H
