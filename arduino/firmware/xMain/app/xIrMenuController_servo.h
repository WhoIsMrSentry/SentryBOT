// Servo-related implementations for IrMenuController
#ifndef SENTRY_APP_IR_MENU_CONTROLLER_SERVO_H
#define SENTRY_APP_IR_MENU_CONTROLLER_SERVO_H

#if IR_ENABLED

#include "xIrMenuController.h"

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

void IrMenuController::applyToken(long v, Robot &robot){
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
    lcdPrint("SERVO:" + String(_servoSel + 1), "DEG:" + String((int)deg));
#if BUZZER_ENABLED
    g_buzzer.beepOn(g_buzzerDefaultOut, 2400, 40);
#endif
    return;
  }
}

#endif // IR_ENABLED

#endif // SENTRY_APP_IR_MENU_CONTROLLER_SERVO_H
