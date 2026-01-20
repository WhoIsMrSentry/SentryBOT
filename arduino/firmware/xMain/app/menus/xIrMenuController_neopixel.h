#ifndef SENTRY_APP_IR_MENU_CONTROLLER_NEOPIXEL_H
#define SENTRY_APP_IR_MENU_CONTROLLER_NEOPIXEL_H

#if IR_ENABLED && NEOPIXEL_ENABLED

#include "../xIrMenuController.h"
#include "../../peripherals/xNeopixel.h"

void IrMenuController::showNeoPixelPrompt(){
  switch(_state){
    case STATE_NEO_MAIN:
      lcdPrint("NEOPIXEL", "1:RGB 2:ANIM");
      break;
    case STATE_NEO_RGB_R:
      lcdPrint("NEO: RED", "VAL(0..255) OK");
      break;
    case STATE_NEO_RGB_G:
      lcdPrint("NEO: GREEN", "VAL(0..255) OK");
      break;
    case STATE_NEO_RGB_B:
      lcdPrint("NEO: BLUE", "VAL(0..255) OK");
      break;
    case STATE_NEO_ANIM:
      lcdPrint("NEO: ANIM", "1..5 OK");
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

// Extends applyToken logic for NeoPixel states
// Note: This needs to be called from the main applyToken or handled in xIrMenuController.h
// Since we are using a separate file, we will add the logic to IrMenuController::applyToken in xIrMenuController_servo.h
// or ideally define it consistently. I will update xIrMenuController_servo.h to dispatch or 
// put everything in a unified place if possible.

// I will actually modify xIrMenuController_servo.h to be more generic or add a new dispatch.
// For now, let's keep it simple and add the logic here if it's not already in xIrMenuController_servo.h

#endif // IR_ENABLED && NEOPIXEL_ENABLED

#endif // SENTRY_APP_IR_MENU_CONTROLLER_NEOPIXEL_H
