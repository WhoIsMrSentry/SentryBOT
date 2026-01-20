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
    return true;
  }

private:
  static String decodeToKey(uint32_t code){
    switch (code){
      case 0xBA45FF00: return "1";
      case 0xB946FF00: return "2";
      case 0xB847FF00: return "3";
      case 0xBB44FF00: return "4";
      case 0xBF40FF00: return "5";
      case 0xBC43FF00: return "6";
      case 0xF807FF00: return "7";
      case 0xEA15FF00: return "8";
      case 0xF609FF00: return "9";
      case 0xE916FF00: return "*";
      case 0xE619FF00: return "0";
      case 0xF20DFF00: return "#";
      case 0xE718FF00: return "UP";
      case 0xF708FF00: return "LEFT";
      case 0xE31CFF00: return "OK";
      case 0xA55AFF00: return "RIGHT";
      case 0xAD52FF00: return "DOWN";
      default: return "UNKNOWN";
    }
  }
};
#endif

#endif // SENTRY_PERIPHERALS_IR_KEY_READER_H
