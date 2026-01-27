#ifndef SENTRY_PERIPHERALS_IR_KEY_READER_H
#define SENTRY_PERIPHERALS_IR_KEY_READER_H

#include <Arduino.h>
#include "../xConfig.h"

#if IR_ENABLED
// Requires Arduino Library: IRremote (v4+)
#include <IRremote.hpp>

class IrKeyReader {
public:
  void begin(uint8_t pin){
    IrReceiver.begin(pin, ENABLE_LED_FEEDBACK);
  }

  // Returns true when a key is decoded; outKey is one of: "0".."9","*","#","UP","DOWN","LEFT","RIGHT","OK","UNKNOWN"
  bool poll(String &outKey){
    uint32_t ignored;
    return poll(outKey, ignored);
  }

  // Same as poll(outKey) but also returns raw decoded data (32-bit) in outCode.
  bool poll(String &outKey, uint32_t &outCode){
    if (!IrReceiver.decode()) return false;
    outCode = IrReceiver.decodedIRData.decodedRawData;
    IrReceiver.resume();
    outKey = decodeToKey(outCode);
    // Do not print raw IR debug output in normal operation.
    return true;
  }

private:
  static String decodeToKey(uint32_t code){
    switch (code){
      case 0xBA45FF00UL: return "1";
      case 0xB946FF00UL: return "2";
      case 0xB847FF00UL: return "3";
      case 0xBB44FF00UL: return "4";
      case 0xBF40FF00UL: return "5";
      case 0xBC43FF00UL: return "6";
      case 0xF807FF00UL: return "7";
      case 0xEA15FF00UL: return "8";
      case 0xF609FF00UL: return "9";
      case 0xE916FF00UL: return "*";
      case 0xE619FF00UL: return "0";
      case 0xF20DFF00UL: return "#";
      case 0xE718FF00UL: return "UP";
      case 0xF708FF00UL: return "LEFT";
      case 0xE31CFF00UL: return "OK";
      case 0xA55AFF00UL: return "RIGHT";
      case 0xAD52FF00UL: return "DOWN";
      default: return "UNKNOWN";
    }
  }
};
#endif

#endif // SENTRY_PERIPHERALS_IR_KEY_READER_H
