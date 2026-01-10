#ifndef SENTRY_PERIPHERALS_ULTRASONIC_H
#define SENTRY_PERIPHERALS_ULTRASONIC_H

#include <Arduino.h>
#include "../xConfig.h"

// Lightweight wrapper to keep xMain clean.
class Ultrasonic {
public:
  void begin(uint8_t trigPin, uint8_t echoPin){
    _trig = trigPin;
    _echo = echoPin;
    pinMode(_trig, OUTPUT);
    pinMode(_echo, INPUT);
    _lastMs = 0;
    _lastCm = NAN;
  }

  // Measure with small timeouts to avoid blocking long.
  bool measureIfDue(unsigned long intervalMs){
    unsigned long now = millis();
    if (now - _lastMs < intervalMs) return false;
    _lastMs = now;

    digitalWrite(_trig, LOW);
    delayMicroseconds(2);
    digitalWrite(_trig, HIGH);
    delayMicroseconds(10);
    digitalWrite(_trig, LOW);

    unsigned long dur = pulseIn(_echo, HIGH, 30000UL); // 30ms timeout ≈ ~5m
    if (dur == 0){
      _lastCm = NAN;
    } else {
      _lastCm = (float)dur / 58.0f;
    }
    return true;
  }

  float lastCm() const { return _lastCm; }

private:
  uint8_t _trig{255};
  uint8_t _echo{255};
  unsigned long _lastMs{0};
  float _lastCm{NAN};
};

#endif // SENTRY_PERIPHERALS_ULTRASONIC_H
