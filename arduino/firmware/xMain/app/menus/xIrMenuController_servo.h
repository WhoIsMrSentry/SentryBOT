// Servo implementations moved into menus/
#ifndef SENTRY_APP_IR_MENU_CONTROLLER_SERVO_H
#define SENTRY_APP_IR_MENU_CONTROLLER_SERVO_H

#if IR_ENABLED

#include "../xIrMenuController.h"

void IrMenuController::showServoPrompt(){
  if (_state == STATE_SERVO_SEL){
    lcdPrint("SERVO", "NUM(1..8) OK");
  } else {
    lcdPrint("SERVO:" + String(_servoSel + 1), "DEG(0..180) OK");
  }
}

void IrMenuController::showServoToken(){
  if (_state == STATE_SERVO_SEL) lcdPrint("SERVO", "N:" + _token + " OK=SET");
  else lcdPrint("SERVO:" + String(_servoSel + 1), "DEG:" + _token + " OK=SET");
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
