#ifndef SENTRY_PERIPHERALS_LASER_PAIR_H
#define SENTRY_PERIPHERALS_LASER_PAIR_H

#include <Arduino.h>
#include "../xConfig.h"

#if LASER_ENABLED
class LaserPair {
public:
  void begin(uint8_t pin1, uint8_t pin2){
    _p1 = pin1;
    _p2 = pin2;
    pinMode(_p1, OUTPUT);
    pinMode(_p2, OUTPUT);
    off();
  }

  void oneOn(uint8_t idx){
    if (idx == 1) digitalWrite(_p1, LASER_ACTIVE_HIGH ? HIGH : LOW);
    else if (idx == 2) digitalWrite(_p2, LASER_ACTIVE_HIGH ? HIGH : LOW);
  }

  void bothOn(){
    digitalWrite(_p1, LASER_ACTIVE_HIGH ? HIGH : LOW);
    digitalWrite(_p2, LASER_ACTIVE_HIGH ? HIGH : LOW);
  }

  void off(){
    digitalWrite(_p1, LASER_ACTIVE_HIGH ? LOW : HIGH);
    digitalWrite(_p2, LASER_ACTIVE_HIGH ? LOW : HIGH);
  }

private:
  uint8_t _p1{255};
  uint8_t _p2{255};
};
#endif

#endif // SENTRY_PERIPHERALS_LASER_PAIR_H
