#ifndef SENTRY_PERIPHERALS_HALL_ENCODER_H
#define SENTRY_PERIPHERALS_HALL_ENCODER_H

#include <Arduino.h>
#include "../xConfig.h"

// Simple, robust hall encoder reader intended for up to a few sensors.
// Uses non-blocking polling (call update() periodically from loop()) to
// detect rising edges. This avoids attachInterrupt() management complexity
// while remaining reliable for user-facing feedback (4 pulses/rev typical).

class HallEncoder {
public:
  HallEncoder() = default;

  // Begin with a digital input pin and number of pulses per revolution
  // Begin with pin and pulses-per-rev. If `analog` is true, reads via analogRead()
  // and uses `threshold` to convert to digital state. Default ppr=1 for single-magnet.
  void begin(uint8_t pin, uint8_t pulsesPerRev = HALL_PULSES_PER_REV, bool analog=false, uint16_t threshold=HALL_ANALOG_THRESHOLD){
    _pin = pin;
    _ppr = pulsesPerRev > 0 ? pulsesPerRev : 1;
    _analog = analog;
    _threshold = threshold;
    if (_analog){
      pinMode(_pin, INPUT);
      int v = analogRead(_pin);
      _lastState = (v >= (int)_threshold) ? HIGH : LOW;
    } else {
      pinMode(_pin, INPUT);
      _lastState = digitalRead(_pin);
    }
    _lastDebounceMs = 0;
    _count = 0;
  }

  // Call frequently from loop(). Debounce and count rising edges.
  void update(){
    unsigned long now = millis();
    int s = LOW;
    if (_analog){
      int v = analogRead(_pin);
      s = (v >= (int)_threshold) ? HIGH : LOW;
    } else {
      s = digitalRead(_pin);
    }
    if (s != _lastState){
      // simple debounce window
      _lastDebounceMs = now;
      _lastState = s;
    } else {
      if (s == HIGH){
        if ((long)(now - _lastDebounceMs) >= (long)_debounceMs){
          if (!_reportedHigh){
            _reportedHigh = true;
            _count++;
          }
        }
      } else {
        _reportedHigh = false;
      }
    }
  }

  // Reset pulse counter
  void reset(){ _count = 0; }

  // Get total pulses counted (monotonic since last reset)
  unsigned long getCount() const { return _count; }

  // Convenience: returns revolutions (float)
  float getRevolutions() const { return (float)_count / (float)_ppr; }

  // Configure debounce in ms (default 6ms)
  void setDebounceMs(unsigned long ms){ _debounceMs = ms; }

  // Explicitly enable analog mode after construction (optional)
  void setAnalogMode(bool a, uint16_t threshold=HALL_ANALOG_THRESHOLD){ _analog = a; _threshold = threshold; }

private:
  uint8_t _pin{255};
  uint8_t _ppr{4};
  bool _analog{false};
  uint16_t _threshold{HALL_ANALOG_THRESHOLD};
  volatile unsigned long _count{0};
  int _lastState{LOW};
  bool _reportedHigh{false};
  unsigned long _lastDebounceMs{0};
  unsigned long _debounceMs{6};
};

// Global placeholders (define in xMain.ino if used)
// extern HallEncoder g_hall0;
// extern HallEncoder g_hall1;

#endif // SENTRY_PERIPHERALS_HALL_ENCODER_H
