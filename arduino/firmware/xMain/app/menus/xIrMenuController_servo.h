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

#if NEOPIXEL_ENABLED
  if (_state == STATE_NEO_MAIN){
    if (v == 1) _state = STATE_NEO_RGB_R;
    else if (v == 2) _state = STATE_NEO_ANIM;
    showNeoPixelPrompt();
    return;
  }
  if (_state == STATE_NEO_RGB_R){
    _neoR = (uint8_t)constrain(v, 0, 255);
    _state = STATE_NEO_RGB_G;
    showNeoPixelPrompt();
    return;
  }
  if (_state == STATE_NEO_RGB_G){
    _neoG = (uint8_t)constrain(v, 0, 255);
    _state = STATE_NEO_RGB_B;
    showNeoPixelPrompt();
    return;
  }
  if (_state == STATE_NEO_RGB_B){
    _neoB = (uint8_t)constrain(v, 0, 255);
    neopixel_start_animation("fill", _neoR, _neoG, _neoB, 0, 0);
    lcdPrint("NEO: SET", "RGB " + String(_neoR) + "," + String(_neoG) + "," + String(_neoB));
    _state = STATE_NEO_MAIN;
    return;
  }
  if (_state == STATE_NEO_ANIM){
    int anim = (int)v;
    String name = "fill";
    if (anim == 1) name = "fill";
    else if (anim == 2) name = "rainbow";
    else if (anim == 3) name = "theater";
    else if (anim == 4) name = "breathe";
    else if (anim == 5) name = "clear";
    neopixel_start_animation(name, _neoR, _neoG, _neoB, 0, 50);
    lcdPrint("NEO: ANIM", name);
    _state = STATE_NEO_MAIN;
    return;
  }
#endif
}

#endif // IR_ENABLED

#endif // SENTRY_APP_IR_MENU_CONTROLLER_SERVO_H
