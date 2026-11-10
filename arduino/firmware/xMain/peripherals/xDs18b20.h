// OneWire / DS18B20 helper for SentryBOT
#ifndef SENTRY_PERIPHERALS_DS18B20_H
#define SENTRY_PERIPHERALS_DS18B20_H

#include <Arduino.h>
#include "../xConfig.h"
#include "../xProtocol.h"

#if DS18_ENABLED
#include <OneWire.h>
#include <DallasTemperature.h>
#if LCD_ENABLED
#include "../app/xLcdHub.h"
#endif
#if BUZZER_ENABLED
#include "xBuzzer.h"
extern BuzzerPair g_buzzer;
#endif

// global alert helper (defined in xMain.ino)
extern void pushAlert(const String &msg);

class Ds18b20Manager {
public:
  void begin(uint8_t pin){
    _pin = pin;
    _oneWire = new OneWire(_pin);
    _sensors = new DallasTemperature(_oneWire);
    _sensors->begin();
    // Use non-blocking async conversions so loop() and steppers never stall for 750ms.
    _sensors->setWaitForConversion(false);
    _deviceCount = _sensors->getDeviceCount();
    SERIAL_IO.print(F("{\"info\":\"ds18_init\",\"devices_found\":"));
    SERIAL_IO.print(_deviceCount);
    SERIAL_IO.println('}');

    // Default labels in requested order:
    // body, driver, right1, right2, left1, left2, head, extra
    static const char* const defNames[DS18_SENSOR_COUNT] = {"body","driver","right1","right2","left1","left2","head","extra"};
    for (uint8_t i=0;i<DS18_SENSOR_COUNT;i++) _names[i] = defNames[i];

    // Capture up to DS18_SENSOR_COUNT addresses (first found devices)
    uint8_t found = min((uint8_t)_deviceCount, (uint8_t)DS18_SENSOR_COUNT);
    for (uint8_t i=0;i<found;i++){
      DeviceAddress addr;
      if (_sensors->getAddress(addr, i)){
        memcpy(_addresses[i], addr, 8);
        _have[i] = true;
      } else {
        _have[i] = false;
      }
    }
    for (uint8_t i=found;i<DS18_SENSOR_COUNT;i++) _have[i] = false;
    for (uint8_t i=0;i<DS18_SENSOR_COUNT;i++) _temps[i] = NAN;
    _state = DS18_IDLE;
    _lastPoll = millis();
    // Kick off first async conversion immediately (harvested ~750ms later in update()).
    if (found > 0) requestConversionAsync();
  }

  void update(){
    if (!_sensors) return;
    unsigned long now = millis();
    if (_state == DS18_CONVERTING){
      if ((long)(now - _convStartMs) >= (long)CONVERSION_WAIT_MS){
        harvestTemperatures();
        _lastPoll = now;
        _state = DS18_IDLE;
      }
      return;
    }
    if ((long)(now - _lastPoll) >= (long)DS18_POLL_MS){
      if (!requestConversionAsync()){
        _lastPoll = now;
      }
    }
  }

  // Non-blocking on-demand trigger: harvests immediately if a conversion is ready,
  // otherwise starts a fresh async conversion while keeping last cached temps available.
  void forceRead(){
    if (!_sensors) return;
    unsigned long now = millis();
    if (_state == DS18_CONVERTING){
      if ((long)(now - _convStartMs) >= (long)CONVERSION_WAIT_MS){
        harvestTemperatures();
        _lastPoll = now;
        _state = DS18_IDLE;
      }
      return;
    }
    requestConversionAsync();
  }

  float tempC(uint8_t idx) const { if (idx>=DS18_SENSOR_COUNT) return NAN; return _temps[idx]; }
  const char* name(uint8_t idx) const { if (idx>=DS18_SENSOR_COUNT) return ""; return _names[idx]; }

private:
  enum State : uint8_t { DS18_IDLE = 0, DS18_CONVERTING = 1 };
  static constexpr unsigned long CONVERSION_WAIT_MS = 750UL;

  bool requestConversionAsync(){
    if (!_sensors || _deviceCount <= 0) return false;
    _sensors->requestTemperatures();
    _convStartMs = millis();
    _state = DS18_CONVERTING;
    return true;
  }

  void harvestTemperatures(){
    if (!_sensors) return;
    for (uint8_t i=0;i<DS18_SENSOR_COUNT;i++){
      if (!_have[i]) continue;
      float t = _sensors->getTempC(_addresses[i]);
      _temps[i] = t;
      // Log reading
      SERIAL_IO.print(F("{\"event\":\"ds18_read\",\"sensor\":\""));
      SERIAL_IO.print(_names[i]);
      SERIAL_IO.print(F("\",\"temp_c\":"));
      if (isnan(t)) SERIAL_IO.print(F("null")); else SERIAL_IO.print(t,2);
      SERIAL_IO.println('}');

      // Hysteresis: clear if below threshold - 2C
      if (!_alertState[i] && !isnan(t) && t >= DS18_OVERHEAT_C){
        triggerAlert(i, t);
      } else if (_alertState[i] && !isnan(t) && t < (DS18_OVERHEAT_C - 2.0f)){
        _alertState[i] = false;
        SERIAL_IO.print(F("{\"event\":\"ds18_cleared\",\"sensor\":\"")); SERIAL_IO.print(_names[i]); SERIAL_IO.println(F("\"}"));
      }
    }
  }
  void triggerAlert(uint8_t idx, float temp){
    _alertState[idx] = true;
#if LCD_ENABLED
    if (lcdHubAny()){
      String top = String(F("OVERHEAT ")) + _names[idx];
      String bottom = String(temp,1) + F(" C");
      g_lcdStatus.showTo(LCD_TGT_1, top, bottom, true);
    }
#endif
    // Add to virtual menu alert history via global helper
    pushAlert(String(F("HOT: ")) + _names[idx]);
#if BUZZER_ENABLED
    // Buzzer: sustained brief warning
    g_buzzer.beepBoth(2000, 500);
#endif
    // Send JSON event so gateway can update neopixels / oled face
    SERIAL_IO.print(F("{\"event\":\"sensor_alert\",\"type\":\"overheat\",\"sensor\":\""));
    SERIAL_IO.print(_names[idx]);
    SERIAL_IO.print(F("\",\"temp_c\":"));
    SERIAL_IO.print(temp,2);
    SERIAL_IO.println('}');

    // Route NeoPixel alert through shared retry/ack queue in xCuteBuzzer.h
    emitNeopixelRequest(String(F("ALERT")), String(F("255,0,0")), 1);
  }

  OneWire* _oneWire{nullptr};
  DallasTemperature* _sensors{nullptr};
  DeviceAddress _addresses[DS18_SENSOR_COUNT];
  bool _have[DS18_SENSOR_COUNT]{};
  bool _alertState[DS18_SENSOR_COUNT]{};
  const char* _names[DS18_SENSOR_COUNT]{};
  float _temps[DS18_SENSOR_COUNT]{};
  unsigned long _lastPoll{0};
  unsigned long _convStartMs{0};
  State _state{DS18_IDLE};
  int _deviceCount{0};
  uint8_t _pin{255};
};

// Declare global instance to be used by main
extern Ds18b20Manager g_ds18;

#endif // DS18_ENABLED

#endif // SENTRY_PERIPHERALS_DS18B20_H
