// Servo implementations moved into menus/
#ifndef SENTRY_APP_IR_MENU_CONTROLLER_SERVO_H
#define SENTRY_APP_IR_MENU_CONTROLLER_SERVO_H

#if IR_ENABLED

#include "../xIrMenuController.h"

void IrMenuController::showServoPrompt(){
  char l1[21], l2[21], l3[21], l4[21];
  if (_state == STATE_SERVO_SEL){
    snprintf_P(l1, sizeof(l1), PSTR(" SELECT SERVO (1-4) "));
    snprintf_P(l2, sizeof(l2), PSTR("  NUM+OK TO SELECT  "));
  } else {
    snprintf_P(l1, sizeof(l1), PSTR("    SERVO %d    "), _servoSel + 1);
    snprintf_P(l2, sizeof(l2), PSTR("  DEG (0-180) + OK  "));
  }
  
  // Show all current poses on lines 3 and 4
  extern Robot robot;
  snprintf_P(l3, sizeof(l3), PSTR(" S1:%3d   S2:%3d "), (int)robot.servos.get(0), (int)robot.servos.get(1));
  snprintf_P(l4, sizeof(l4), PSTR(" S3:%3d   S4:%3d "), (int)robot.servos.get(2), (int)robot.servos.get(3));
  g_lcdStatus.show4To(LCD_TGT_1, l1, l2, l3, l4, true);
}

void IrMenuController::showServoToken(){
  char l1[21], l2[21], l3[21], l4[21];
  if (_state == STATE_SERVO_SEL){
    snprintf_P(l1, sizeof(l1), PSTR(" SELECT SERVO (1-4) "));
    snprintf_P(l2, sizeof(l2), PSTR("  INPUT N: %-8s "), _token.c_str());
  } else {
    snprintf_P(l1, sizeof(l1), PSTR("    SERVO %d    "), _servoSel + 1);
    snprintf_P(l2, sizeof(l2), PSTR(" INPUT DEG: %-7s"), _token.c_str());
  }
  
  extern Robot robot;
  snprintf_P(l3, sizeof(l3), PSTR(" S1:%3d   S2:%3d "), (int)robot.servos.get(0), (int)robot.servos.get(1));
  snprintf_P(l4, sizeof(l4), PSTR(" S3:%3d   S4:%3d "), (int)robot.servos.get(2), (int)robot.servos.get(3));
  g_lcdStatus.show4To(LCD_TGT_1, l1, l2, l3, l4, true);
}

void IrMenuController::startToken(){
  _capture = true;
  _token = "";
  _lastDigitMs = 0;
}

void IrMenuController::cancelToken(){
  _capture = false;
  _token = "";
  _lastDigitMs = 0;
}

void IrMenuController::commitTokenIfAny(Robot &robot){
  if (_token.length() == 0) return;
  long v = _token.toInt();
  applyToken(v, robot);
  _token = "";
  _lastDigitMs = 0;
}

#endif // IR_ENABLED

#endif // SENTRY_APP_IR_MENU_CONTROLLER_SERVO_H
