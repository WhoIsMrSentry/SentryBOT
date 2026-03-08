#ifndef X_NEMA_CONTROLLER_H
#define X_NEMA_CONTROLLER_H

#include <Arduino.h>
#include "xStepperPair.h"
#include "../peripherals/xEbyteRadio.h"
#include "../xConfig.h"

class NemaController {
public:
  NemaController(StepperPair* pair, EbyteRadio* radio);
  void begin();
  void update(); // poll radio packets and drive steppers
  void setEnabled(bool en);
  bool isEnabled() const;
  bool isLeftMotorEnabled() const;
  bool isRightMotorEnabled() const;

private:
  StepperPair* steppers;
  EbyteRadio* radio;
  bool leftEnabled{false};
  bool rightEnabled{false};
  float maxSpeedStepsPerSec{SKATE_SPEED_LIMIT};
  bool _enabled{true};
  void applyJoystick(int8_t x, int8_t y);
};

extern NemaController g_nema;

#endif // X_NEMA_CONTROLLER_H
