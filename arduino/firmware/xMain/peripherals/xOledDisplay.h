#ifndef SENTRY_PERIPHERALS_OLED_H
#define SENTRY_PERIPHERALS_OLED_H

#include <Arduino.h>
#include "../xConfig.h"

#if defined(OLED_ENABLED) && OLED_ENABLED
#ifndef OLED_ALLOW_STUB
#define OLED_ALLOW_STUB 0
#endif

#if !OLED_ALLOW_STUB
#define OLED_SSD1306_AVAILABLE 1
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#else
#if defined(__has_include) && __has_include(<Adafruit_SSD1306.h>)
#define OLED_SSD1306_AVAILABLE 1
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#else
#define OLED_SSD1306_AVAILABLE 0
#endif
#endif

#if OLED_SSD1306_AVAILABLE
#if defined(__has_include) && __has_include(<Irisoled.h>)
#include <Irisoled.h>
#define IRISOLED_LIB_AVAILABLE 1
#elif defined(__has_include) && __has_include(<IrisOled.h>)
#include <IrisOled.h>
#define IRISOLED_LIB_AVAILABLE 1
#else
#define IRISOLED_LIB_AVAILABLE 0
#endif

class OledDisplay {
public:
  bool begin(uint8_t addr = OLED_I2C_ADDR, uint8_t w = 128, uint8_t h = 64){
    _addr = addr; _w = w; _h = h;
#if defined(ARDUINO_ARCH_AVR)
    Wire.begin();
#else
    Wire.begin();
#endif
    if (!_display){
      _display = new Adafruit_SSD1306(_w, _h, &Wire);
    }
    if (!_display->begin(SSD1306_SWITCHCAPVCC, _addr)) return false;
    _display->clearDisplay();
    _display->setTextSize(1);
    _display->setTextColor(SSD1306_WHITE);
    _display->display();
    return true;
  }

  void update(){
#if IRISOLED_LIB_AVAILABLE
    if (!_display || !_anim.running) return;
    unsigned long now = millis();
    if (now - _anim.last_ms < _anim.delay_ms) return;
    _anim.last_ms = now;
    const unsigned char* bmp = _nextFrame();
    if (bmp) drawBitmapByPtr(bmp);
#endif
  }

  void showLogo(){
    if (!_display) return;
#if IRISOLED_LIB_AVAILABLE
    stopAnimation();
    drawBitmapByPtr(Irisoled::normal);
#else
    _display->clearDisplay();
    _display->drawRect(0, 0, _w, _h, SSD1306_WHITE);
    _display->setTextSize(2);
    _display->setTextColor(SSD1306_WHITE);
    _display->setCursor(26, 22);
    _display->print(F("OLED"));
    _display->display();
#endif
  }

  bool showBitmapByName(const String &name){
#if IRISOLED_LIB_AVAILABLE
    const unsigned char* bmp = resolveBitmap(name);
    if (!bmp) return false;
    stopAnimation();
    drawBitmapByPtr(bmp);
    return true;
#else
    String n = name;
    n.trim();
    n.toLowerCase();
  if (n == "logo" || n == "normal") { showLogo(); return true; }
    return false;
#endif
  }

  bool startAnimationByName(const String &name){
#if IRISOLED_LIB_AVAILABLE
    String n = normalize(name);
    if (n == "wink"){
      static const unsigned char* const frames[] = { Irisoled::normal, Irisoled::wink_left, Irisoled::normal, Irisoled::wink_right, Irisoled::normal };
      return setAnim(frames, sizeof(frames)/sizeof(frames[0]), 140);
    }
    if (n == "blink"){
      static const unsigned char* const frames[] = { Irisoled::normal, Irisoled::blink_up, Irisoled::blink, Irisoled::blink_down, Irisoled::normal };
      return setAnim(frames, sizeof(frames)/sizeof(frames[0]), 120);
    }
    if (n == "scan"){
      static const unsigned char* const frames[] = { Irisoled::normal, Irisoled::look_left, Irisoled::look_right, Irisoled::look_up, Irisoled::look_down, Irisoled::normal };
      return setAnim(frames, sizeof(frames)/sizeof(frames[0]), 170);
    }
    if (n == "sleep"){
      static const unsigned char* const frames[] = { Irisoled::sleepy, Irisoled::blink_down, Irisoled::blink, Irisoled::blink_up, Irisoled::sleepy };
      return setAnim(frames, sizeof(frames)/sizeof(frames[0]), 260);
    }
    if (n == "alert"){
      static const unsigned char* const frames[] = { Irisoled::alert, Irisoled::focused, Irisoled::warning, Irisoled::furious, Irisoled::alert };
      return setAnim(frames, sizeof(frames)/sizeof(frames[0]), 130);
    }
    if (n == "emotive"){
      static const unsigned char* const frames[] = { Irisoled::happy, Irisoled::excited, Irisoled::surprised, Irisoled::sad, Irisoled::worried, Irisoled::normal };
      return setAnim(frames, sizeof(frames)/sizeof(frames[0]), 170);
    }
    if (n == "icons"){
      static const unsigned char* const frames[] = { Irisoled::logo, Irisoled::mode, Irisoled::left_signal, Irisoled::right_signal, Irisoled::battery_low, Irisoled::battery, Irisoled::battery_full, Irisoled::warning };
      return setAnim(frames, sizeof(frames)/sizeof(frames[0]), 260);
    }
    if (n == "all"){
      static const unsigned char* const frames[] = {
        Irisoled::alert, Irisoled::angry, Irisoled::blink_down, Irisoled::blink_up, Irisoled::blink,
        Irisoled::bored, Irisoled::despair, Irisoled::disoriented, Irisoled::excited, Irisoled::focused,
        Irisoled::furious, Irisoled::happy, Irisoled::look_down, Irisoled::look_left, Irisoled::look_right,
        Irisoled::look_up, Irisoled::normal, Irisoled::sad, Irisoled::scared, Irisoled::sleepy,
        Irisoled::surprised, Irisoled::wink_left, Irisoled::wink_right, Irisoled::worried,
        Irisoled::battery_full, Irisoled::battery_low, Irisoled::battery, Irisoled::left_signal,
        Irisoled::logo, Irisoled::mode, Irisoled::right_signal, Irisoled::warning
      };
      return setAnim(frames, sizeof(frames)/sizeof(frames[0]), 180);
    }
    return false;
#else
    (void)name;
    return false;
#endif
  }

  void stopAnimation(){
#if IRISOLED_LIB_AVAILABLE
    _anim.running = false;
    _anim.frames = nullptr;
    _anim.count = 0;
    _anim.index = 0;
#endif
  }

  static const char* bitmapCatalog(){
#if IRISOLED_LIB_AVAILABLE
    return "alert,angry,blink_down,blink_up,blink,bored,despair,disoriented,excited,focused,furious,happy,look_down,look_left,look_right,look_up,normal,sad,scared,sleepy,surprised,wink_left,wink_right,worried,battery_full,battery_low,battery,left_signal,logo,mode,right_signal,warning";
#else
    return "logo";
#endif
  }

  static const char* animationCatalog(){
    return "wink,blink,scan,sleep,alert,emotive,icons,all";
  }

  static const char* backendName(){
#if IRISOLED_LIB_AVAILABLE
    return "ssd1306_irisoled";
#else
    return "ssd1306_only";
#endif
  }

  static bool isStub(){ return false; }

private:
  uint8_t _addr{OLED_I2C_ADDR};
  uint8_t _w{128}, _h{64};
  Adafruit_SSD1306 *_display{nullptr};

#if IRISOLED_LIB_AVAILABLE
  struct AnimState {
    const unsigned char* const* frames{nullptr};
    uint8_t count{0};
    uint8_t index{0};
    uint16_t delay_ms{180};
    unsigned long last_ms{0};
    bool running{false};
  } _anim;

  static String normalize(const String &s){
    String n = s;
    n.trim();
    n.toLowerCase();
    return n;
  }

  bool setAnim(const unsigned char* const* frames, uint8_t count, uint16_t delayMs){
    if (!frames || count == 0) return false;
    _anim.frames = frames;
    _anim.count = count;
    _anim.index = 0;
    _anim.delay_ms = delayMs;
    _anim.last_ms = 0;
    _anim.running = true;
    drawBitmapByPtr(_anim.frames[0]);
    return true;
  }

  const unsigned char* _nextFrame(){
    if (!_anim.running || !_anim.frames || _anim.count == 0) return nullptr;
    _anim.index = (uint8_t)((_anim.index + 1) % _anim.count);
    return _anim.frames[_anim.index];
  }

  void drawBitmapByPtr(const unsigned char* bmp){
    if (!_display || !bmp) return;
    _display->clearDisplay();
    _display->drawBitmap(0, 0, bmp, _w, _h, SSD1306_WHITE);
    _display->display();
  }

  static const unsigned char* resolveBitmap(const String &name){
    String n = normalize(name);
    if (n == "alert") return Irisoled::alert;
    if (n == "angry") return Irisoled::angry;
    if (n == "blink_down") return Irisoled::blink_down;
    if (n == "blink_up") return Irisoled::blink_up;
    if (n == "blink") return Irisoled::blink;
    if (n == "bored") return Irisoled::bored;
    if (n == "despair") return Irisoled::despair;
    if (n == "disoriented") return Irisoled::disoriented;
    if (n == "excited") return Irisoled::excited;
    if (n == "focused") return Irisoled::focused;
    if (n == "furious") return Irisoled::furious;
    if (n == "happy") return Irisoled::happy;
    if (n == "look_down") return Irisoled::look_down;
    if (n == "look_left") return Irisoled::look_left;
    if (n == "look_right") return Irisoled::look_right;
    if (n == "look_up") return Irisoled::look_up;
    if (n == "normal") return Irisoled::normal;
    if (n == "sad") return Irisoled::sad;
    if (n == "scared") return Irisoled::scared;
    if (n == "sleepy") return Irisoled::sleepy;
    if (n == "surprised") return Irisoled::surprised;
    if (n == "wink_left") return Irisoled::wink_left;
    if (n == "wink_right") return Irisoled::wink_right;
    if (n == "worried") return Irisoled::worried;
    if (n == "battery_full") return Irisoled::battery_full;
    if (n == "battery_low") return Irisoled::battery_low;
    if (n == "battery") return Irisoled::battery;
    if (n == "left_signal") return Irisoled::left_signal;
    if (n == "logo") return Irisoled::logo;
    if (n == "mode") return Irisoled::mode;
    if (n == "right_signal") return Irisoled::right_signal;
    if (n == "warning") return Irisoled::warning;
    return nullptr;
  }

#endif
};
#else
// If Adafruit_SSD1306 not available, provide a stub so firmware still compiles
class OledDisplay {
public:
  bool begin(uint8_t = 0x3C, uint8_t = 128, uint8_t = 64){ return false; }
  void showLogo() {}
  bool showBitmapByName(const String &){ return false; }
  bool startAnimationByName(const String &){ return false; }
  void stopAnimation() {}
  void update() {}
  static const char* bitmapCatalog(){ return ""; }
  static const char* animationCatalog(){ return ""; }
  static const char* backendName(){ return "stub_no_ssd1306"; }
  static bool isStub(){ return true; }
};
#endif // include check
#else
// OLED disabled -> empty stub
class OledDisplay {
public:
  bool begin(uint8_t=0){ return false; }
  void showLogo(){}
  bool showBitmapByName(const String &){ return false; }
  bool startAnimationByName(const String &){ return false; }
  void stopAnimation() {}
  void update() {}
  static const char* bitmapCatalog(){ return ""; }
  static const char* animationCatalog(){ return ""; }
  static const char* backendName(){ return "oled_disabled"; }
  static bool isStub(){ return true; }
};
#endif // OLED_ENABLED

#endif // SENTRY_PERIPHERALS_OLED_H
