#ifndef SENTRY_PERIPHERALS_OLED_H
#define SENTRY_PERIPHERALS_OLED_H

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "../xConfig.h"

#ifndef OLED_RESET_PIN
#define OLED_RESET_PIN -1
#endif

#ifndef OLED_USE_IRISOLED
#define OLED_USE_IRISOLED 0
#endif

#if OLED_USE_IRISOLED
#include <Irisoled.h>
#define IRISOLED_LIB_AVAILABLE 1
#else
#define IRISOLED_LIB_AVAILABLE 0
#endif

class OledDisplay {
public:
  bool begin(uint8_t addr = OLED_I2C_ADDR, uint8_t w = OLED_WIDTH, uint8_t h = OLED_HEIGHT) {
    _addr = addr;
    _w = w;
    _h = h;

    Wire.begin();
    delay(60);

    if (!_display.begin(SSD1306_SWITCHCAPVCC, _addr)) {
      return false;
    }

    _display.clearDisplay();
    _display.setTextColor(SSD1306_WHITE);
    _display.display();
    return true;
  }

  void update() {
#if IRISOLED_LIB_AVAILABLE
    if (!_anim.running || !_anim.frames || _anim.count == 0) return;
    unsigned long now = millis();
    if (now - _anim.lastMs < _anim.delayMs) return;
    _anim.lastMs = now;
    _anim.index = (uint8_t)((_anim.index + 1) % _anim.count);
    drawBitmapByPtr(_anim.frames[_anim.index]);
#endif
  }

  void showLogo() {
#if IRISOLED_LIB_AVAILABLE
    stopAnimation();
    drawBitmapByPtr(Irisoled::normal);
#else
    stopAnimation();
    _display.clearDisplay();
    _display.setTextSize(2);
    _display.setTextColor(SSD1306_WHITE);
    _display.setCursor(16, 24);
    _display.print(F("SENTRY"));
    _display.display();
#endif
  }

  void showTestPattern() {
    stopAnimation();
    _display.clearDisplay();
    for (uint8_t y = 0; y < _h; y += 8) {
      for (uint8_t x = 0; x < _w; x += 8) {
        if ((((x / 8) + (y / 8)) & 1) == 0) {
          _display.fillRect(x, y, 8, 8, SSD1306_WHITE);
        }
      }
    }
    _display.drawRect(0, 0, _w, _h, SSD1306_WHITE);
    _display.setTextSize(1);
    _display.setTextColor(SSD1306_WHITE, SSD1306_BLACK);
    _display.setCursor(2, 2);
    _display.print(F("OLED TEST"));
    _display.display();
  }

  void rawDiag() {
    Wire.begin();
    Wire.beginTransmission(_addr);
    uint8_t ack = Wire.endTransmission();
    SERIAL_IO.println(String("{\"diag\":\"i2c_ack\",\"addr\":\"0x") + String(_addr, HEX) + String("\",\"ok\":") + String(ack == 0 ? "true" : "false") + String("}"));

    bool ok = _display.begin(SSD1306_SWITCHCAPVCC, _addr);
    _display.clearDisplay();
    _display.fillRect(0, 0, _w, _h, SSD1306_WHITE);
    _display.display();
    SERIAL_IO.println(String("{\"diag\":\"ssd1306_begin\",\"ok\":") + String(ok ? "true" : "false") + String("}"));
  }

  bool showBitmapByName(const String &name) {
    String n = normalize(name);

#if IRISOLED_LIB_AVAILABLE
    const unsigned char* bmp = resolveBitmap(n);
    if (!bmp) return false;
    stopAnimation();
    drawBitmapByPtr(bmp);
    return true;
#else
    if (n.length() == 0 || n == "normal" || n == "logo") {
      showLogo();
      return true;
    }
    stopAnimation();
    _display.clearDisplay();
    _display.setTextSize(1);
    _display.setTextColor(SSD1306_WHITE);
    _display.setCursor(0, 0);
    _display.print(F("face:"));
    _display.setCursor(0, 12);
    _display.print(n);
    _display.display();
    return true;
#endif
  }

  bool startAnimationByName(const String &name) {
#if IRISOLED_LIB_AVAILABLE
    String n = normalize(name);
    if (n == "wink") {
      static const unsigned char* const frames[] = { Irisoled::normal, Irisoled::wink_left, Irisoled::normal, Irisoled::wink_right, Irisoled::normal };
      return setAnim(frames, sizeof(frames) / sizeof(frames[0]), 160);
    }
    if (n == "blink") {
      static const unsigned char* const frames[] = { Irisoled::normal, Irisoled::blink_up, Irisoled::blink, Irisoled::blink_down, Irisoled::normal };
      return setAnim(frames, sizeof(frames) / sizeof(frames[0]), 130);
    }
    if (n == "scan") {
      static const unsigned char* const frames[] = { Irisoled::look_left, Irisoled::normal, Irisoled::look_right, Irisoled::normal };
      return setAnim(frames, sizeof(frames) / sizeof(frames[0]), 180);
    }
    if (n == "sleep") {
      static const unsigned char* const frames[] = { Irisoled::sleepy, Irisoled::blink_down, Irisoled::blink, Irisoled::sleepy };
      return setAnim(frames, sizeof(frames) / sizeof(frames[0]), 240);
    }
    if (n == "alert") {
      static const unsigned char* const frames[] = { Irisoled::alert, Irisoled::focused, Irisoled::warning, Irisoled::alert };
      return setAnim(frames, sizeof(frames) / sizeof(frames[0]), 130);
    }
    if (n == "emotive") {
      static const unsigned char* const frames[] = { Irisoled::happy, Irisoled::surprised, Irisoled::sad, Irisoled::normal };
      return setAnim(frames, sizeof(frames) / sizeof(frames[0]), 180);
    }
    if (n == "icons") {
      static const unsigned char* const frames[] = { Irisoled::logo, Irisoled::left_signal, Irisoled::right_signal, Irisoled::battery, Irisoled::warning };
      return setAnim(frames, sizeof(frames) / sizeof(frames[0]), 260);
    }
    if (n == "all") {
      static const unsigned char* const frames[] = {
        Irisoled::normal, Irisoled::happy, Irisoled::sad, Irisoled::angry, Irisoled::worried,
        Irisoled::scared, Irisoled::alert, Irisoled::look_left, Irisoled::look_right, Irisoled::surprised
      };
      return setAnim(frames, sizeof(frames) / sizeof(frames[0]), 170);
    }
    return false;
#else
    (void)name;
    return false;
#endif
  }

  void stopAnimation() {
#if IRISOLED_LIB_AVAILABLE
    _anim.running = false;
    _anim.frames = nullptr;
    _anim.count = 0;
    _anim.index = 0;
#endif
  }

  static const char* bitmapCatalog() {
#if IRISOLED_LIB_AVAILABLE
    return "alert,angry,blink_down,blink_up,blink,bored,despair,disoriented,excited,focused,furious,happy,look_down,look_left,look_right,look_up,normal,sad,scared,sleepy,surprised,wink_left,wink_right,worried,battery_full,battery_low,battery,left_signal,logo,mode,right_signal,warning";
#else
    return "logo,normal";
#endif
  }

  static const char* animationCatalog() {
#if IRISOLED_LIB_AVAILABLE
    return "wink,blink,scan,sleep,alert,emotive,icons,all";
#else
    return "";
#endif
  }

  static const char* backendName() {
#if IRISOLED_LIB_AVAILABLE
    return "ssd1306_irisoled";
#else
    return "ssd1306_only";
#endif
  }

  static bool isStub() { return false; }

private:
  uint8_t _addr{OLED_I2C_ADDR};
  uint8_t _w{OLED_WIDTH};
  uint8_t _h{OLED_HEIGHT};
  Adafruit_SSD1306 _display{OLED_WIDTH, OLED_HEIGHT, &Wire, OLED_RESET_PIN};

  static String normalize(const String &name) {
    String n = name;
    n.toLowerCase();
    n.trim();
    n.replace(' ', '_');
    n.replace('-', '_');
    return n;
  }

#if IRISOLED_LIB_AVAILABLE
  struct AnimState {
    const unsigned char* const* frames{nullptr};
    uint8_t count{0};
    uint8_t index{0};
    uint16_t delayMs{180};
    unsigned long lastMs{0};
    bool running{false};
  } _anim;

  bool setAnim(const unsigned char* const* frames, uint8_t count, uint16_t delayMs) {
    if (!frames || count == 0) return false;
    _anim.frames = frames;
    _anim.count = count;
    _anim.index = 0;
    _anim.delayMs = delayMs;
    _anim.lastMs = 0;
    _anim.running = true;
    drawBitmapByPtr(_anim.frames[0]);
    return true;
  }

  void drawBitmapByPtr(const unsigned char* bmp) {
    if (!bmp) return;
    _display.clearDisplay();
    _display.drawBitmap(0, 0, bmp, _w, _h, SSD1306_WHITE);
    _display.display();
  }

  static const unsigned char* resolveBitmap(const String &n) {
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

#endif
