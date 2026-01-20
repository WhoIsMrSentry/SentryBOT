#ifndef SENTRY_APP_IR_MENU_CONTROLLER_NEOPIXEL_H
#define SENTRY_APP_IR_MENU_CONTROLLER_NEOPIXEL_H

#if IR_ENABLED && NEOPIXEL_ENABLED

#include "../xIrMenuController.h"
#include "../../peripherals/xNeopixel.h"

#define NEO_ANIM_COUNT 5

static String neoAnimName(uint8_t idx){
  switch(idx){
    case 0: return "RAINBOW";
    case 1: return "BREATHE";
    case 2: return "THEATER";
    case 3: return "FILL";
    case 4: return "CLEAR";
    default: return "ANIM";
  }
}

static String neoAnimCmd(uint8_t idx){
  switch(idx){
    case 0: return "rainbow";
    case 1: return "breathe";
    case 2: return "theater";
    case 3: return "fill";
    case 4: return "clear";
    default: return "fill";
  }
}

void IrMenuController::showNeoPixelPrompt(){
  switch(_state){
    case STATE_NEO_MAIN:
      lcdPrint("NEOPIXEL", "1:RGB 2:ANIM");
      break;
    case STATE_NEO_RGB_R:
      lcdPrint("NEO: RED", "VAL:0..255 OK");
      break;
    case STATE_NEO_RGB_G:
      lcdPrint("NEO: GREEN", "VAL:0..255 OK");
      break;
    case STATE_NEO_RGB_B:
      lcdPrint("NEO: BLUE", "VAL:0..255 OK");
      break;
    case STATE_NEO_ANIM:
      lcdPrint("NEO: ANIM", neoAnimName(_neoAnimIndex) + " OK=SET");
      break;
    default:
      break;
  }
}

void IrMenuController::showNeoPixelToken(){
  String label = "";
  switch(_state){
    case STATE_NEO_MAIN: label = "SELECT"; break;
    case STATE_NEO_RGB_R: label = "RED"; break;
    case STATE_NEO_RGB_G: label = "GREEN"; break;
    case STATE_NEO_RGB_B: label = "BLUE"; break;
    case STATE_NEO_ANIM: label = "ANIM"; break;
    default: break;
  }
  lcdPrint("NEO:" + label, "VAL:" + _token + " OK=SET");
}

void IrMenuController::handleNeoPixelKey(const String &k, Robot &robot){
  if (k == "UP" && _state == STATE_NEO_ANIM){
    if (_neoAnimIndex == 0) _neoAnimIndex = NEO_ANIM_COUNT - 1;
    else _neoAnimIndex--;
    showNeoPixelPrompt();
    return;
  }
  if (k == "DOWN" && _state == STATE_NEO_ANIM){
    _neoAnimIndex = (_neoAnimIndex + 1) % NEO_ANIM_COUNT;
    showNeoPixelPrompt();
    return;
  }
  if (k == "*"){
    startToken();
    showNeoPixelToken();
    return;
  }
  if (k == "OK"){
    if (_state == STATE_NEO_ANIM){
      neopixel_start_animation(neoAnimCmd(_neoAnimIndex), _neoR, _neoG, _neoB, 0, 50);
      lcdPrint("NEO: ANIM", neoAnimName(_neoAnimIndex));
      _state = STATE_NEO_MAIN;
      return;
    }
    commitTokenIfAny(robot);
    _capture = false;
    _token = "";
    showNeoPixelPrompt();
    return;
  }
  if (isDigitKey(k)){
    if (!_capture){
      _capture = true;
      _token = "";
    }
    _token += k;
    _lastDigitMs = millis();
    showNeoPixelToken();
    return;
  }
}

#endif // IR_ENABLED && NEOPIXEL_ENABLED

#endif // SENTRY_APP_IR_MENU_CONTROLLER_NEOPIXEL_H
