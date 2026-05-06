// OneWire / DS18B20 helper for SentryBOT
#ifndef SENTRY_PERIPHERALS_DS18B20_H
#define SENTRY_PERIPHERALS_DS18B20_H

#include <Arduino.h>
#include "../xConfig.h"
#include "../xProtocol.h"

#if DS18_ENABLED
#include <OneWire.h>
#include <DallasTemperature.h>
#include "../app/xLcdHub.h"
#include "xBuzzer.h"

// buzzer instance (defined in xMain.ino)
extern BuzzerPair g_buzzer;

// global alert helper (defined in xMain.ino)
extern void pushAlert(const String &msg);

class Ds18b20Manager {
public:
  void begin(uint8_t pin){
    _pin = pin;
    _oneWire = new OneWire(_pin);
    _sensors = new DallasTemperature(_oneWire);
    _sensors->begin();
    delay(200); // Wait for bus to stabilize
    _deviceCount = _sensors->getDeviceCount();
    SERIAL_IO.print(F("{\"info\":\"ds18_init\",\"devices_found\":"));
    SERIAL_IO.print(_deviceCount);
    SERIAL_IO.println(F("}"));

    // Default labels in requested order:
    // body, driver, right1, right2, left1, left2, head, extra
    static const char* defNames[DS18_SENSOR_COUNT] = {"body","driver","right1","right2","left1","left2","head","extra"};
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
    _lastPoll = 0;
    // Prime values immediately so menus/web do not show stale/empty data.
    forceRead();
  }

  void update(){
    unsigned long now = millis();
    if ((long)(now - _lastPoll) < (long)DS18_POLL_MS) return;
    _lastPoll = now;
    performRead();
  }

  void forceRead(){
    _lastPoll = millis();
    performRead();
  }

  float tempC(uint8_t idx) const { if (idx>=DS18_SENSOR_COUNT) return NAN; return _temps[idx]; }
  const char* name(uint8_t idx) const { if (idx>=DS18_SENSOR_COUNT) return ""; return _names[idx]; }

private:
  void performRead(){
    if (!_sensors) return;
    _sensors->requestTemperatures();
    for (uint8_t i=0;i<DS18_SENSOR_COUNT;i++){
      if (!_have[i]) continue;
      float t = _sensors->getTempC(_addresses[i]);
      _temps[i] = t;
      // Log reading
      SERIAL_IO.print(F("{\"event\":\"ds18_read\",\"sensor\":\""));
      SERIAL_IO.print(_names[i]);
      SERIAL_IO.print(F("\",\"temp_c\":"));
      if (isnan(t)) SERIAL_IO.print(F("null")); else SERIAL_IO.print(t,2);
      SERIAL_IO.println(F("}"));

      // Hysteresis: clear if below threshold - 2C
      if (!_alertState[i] && !isnan(t) && t >= DS18_OVERHEAT_C){
        triggerAlert(i, t);
      } else if (_alertState[i] && !isnan(t) && t < (DS18_OVERHEAT_C - 2.0f)){
        // clear alert
        _alertState[i] = false;
        SERIAL_IO.print(F("{\"event\":\"ds18_cleared\",\"sensor\":\"")); SERIAL_IO.print(_names[i]); SERIAL_IO.println(F("\"}"));
      }
    }
  }
  void triggerAlert(uint8_t idx, float temp){
    _alertState[idx] = true;
    // LCD
    if (lcdHubAny()){
      String top = String("OVERHEAT ") + _names[idx];
      String bottom = String(temp,1) + String(" C");
      g_lcdStatus.showTo(LCD_TGT_1, top, bottom, true);
    }
    // Add to IR menu alert history via global helper
    pushAlert(String("HOT: ") + _names[idx]);
    // Buzzer: sustained brief both outputs
    g_buzzer.beepBoth(2000, 500);
    // Send JSON event so gateway can update neopixels / oled face
    SERIAL_IO.print(F("{\"event\":\"sensor_alert\",\"type\":\"overheat\",\"sensor\":\""));
    SERIAL_IO.print(_names[idx]);
    SERIAL_IO.print(F("\",\"temp_c\":"));
    SERIAL_IO.print(temp,2);
    SERIAL_IO.println(F("}"));

    // Also request NeoPixel animation on the Pi (Pi runs Neo + OLED)
    // Include a short seq so gateway can ACK and rate-limit if needed.
    _seq = (_seq + 1) & 0x7FFFFFFF;
    SERIAL_IO.print(F("{\"event\":\"neopixel_request\",\"name\":\"ALERT\",\"color\":\"255,0,0\",\"segment\":\""));
    SERIAL_IO.print(_names[idx]);
    SERIAL_IO.print(F("\",\"seq\":")); SERIAL_IO.print(_seq);
    SERIAL_IO.println(F("}"));
  }

  OneWire* _oneWire{nullptr};
  DallasTemperature* _sensors{nullptr};
  DeviceAddress _addresses[DS18_SENSOR_COUNT];
  bool _have[DS18_SENSOR_COUNT]{};
  bool _alertState[DS18_SENSOR_COUNT]{};
  const char* _names[DS18_SENSOR_COUNT]{};
  float _temps[DS18_SENSOR_COUNT]{};
  unsigned long _lastPoll{0};
  int _deviceCount{0};
  uint8_t _pin{255};
  unsigned long _seq{0};
};

// Declare global instance to be used by main
extern Ds18b20Manager g_ds18;

#endif // DS18_ENABLED

#endif // SENTRY_PERIPHERALS_DS18B20_H
