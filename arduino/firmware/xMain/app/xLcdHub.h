#ifndef SENTRY_APP_LCD_HUB_H
#define SENTRY_APP_LCD_HUB_H

#include <Arduino.h>
#include <Wire.h>
#include "../xConfig.h"
#include "../xProtocol.h"

// Shared LCD hub routing constants.
static constexpr uint8_t LCD_TGT_1 = 0x01;

// Shared I2C presence probe (available even when LCD_ENABLED == 0 for boot diagnostics)
static inline bool i2cDevicePresent(uint8_t addr){
  Wire.beginTransmission(addr);
  uint8_t st = Wire.endTransmission();
  Protocol::pollWireTimeout();
  return (st == 0);
}

#if LCD_ENABLED
#include "../xPeripherals.h"

// Globals owned by xMain.ino
extern LcdDisplay g_lcd1;
extern bool g_lcd1Ok;

static inline void bootInfo(const char *name, bool ok){
  SERIAL_IO.print(F("{\"info\":\"boot_check\",\"name\":\""));
  SERIAL_IO.print(name);
  SERIAL_IO.print(F("\",\"ok\":"));
  SERIAL_IO.print(ok ? F("true") : F("false"));
  SERIAL_IO.println('}');
}

static inline uint8_t lcdHubAvailableMask(){
  uint8_t m = 0;
  if (g_lcd1Ok) m |= LCD_TGT_1;
  return m;
}

static inline bool lcdHubAny(){
  return lcdHubAvailableMask() != 0;
}

static inline uint8_t lcdHubResolveMask(uint8_t requested){
  uint8_t avail = lcdHubAvailableMask();
  uint8_t resolved = (requested & avail);
  // If requested mask doesn't match any connected display, fallback to whatever is available.
  return (resolved == 0) ? avail : resolved;
}

static inline void lcdHubPrint4(uint8_t requestedMask, const String &l1, const String &l2, const String &l3, const String &l4){
  uint8_t m = lcdHubResolveMask(requestedMask);
  if ((m & LCD_TGT_1) && g_lcd1Ok) g_lcd1.print4Lines(l1, l2, l3, l4);
}

// Soft repaint hook for state transitions. The display content itself is not
// hardware-cleared — subsequent `print4Lines` calls always pad each row to the
// full column width with spaces, which guarantees stale pixels are overwritten
// without the side effects of `LiquidCrystal_I2C::clear()` on flaky panels.
static inline void lcdHubFullClear(uint8_t requestedMask){
  uint8_t m = lcdHubResolveMask(requestedMask);
  if ((m & LCD_TGT_1) && g_lcd1Ok) g_lcd1.repaint();
}

// 2-line entry routes through print4Lines so lower rows never keep stale content.
static inline void lcdHubPrint(uint8_t requestedMask, const String &top, const String &bottom){
  lcdHubPrint4(requestedMask, top, bottom, String(""), String(""));
}

static inline void lcdHubPrintDefault(const String &top, const String &bottom){
  lcdHubPrint(LCD_TGT_1, top, bottom);
}

static inline void bootUiStep(const String &top, const String &bottom, unsigned long ms){
  if (!BOOT_UI_ENABLED) return;
  if (!lcdHubAny()) return;

  // Center for 20x4
  String t = top;
  while (t.length() < 20) {
    if (t.length() % 2 == 0) t = " " + t;
    else t = t + " ";
  }
  String b = bottom;
  while (b.length() < 20) {
    if (b.length() % 2 == 0) b = " " + b;
    else b = b + " ";
  }

  lcdHubPrintDefault(t, b);

  unsigned long t0 = millis();
  while (millis() - t0 < ms){
    // Do not read or consume SERIAL_IO bytes during boot splash so NDJSON framing stays intact.
    delay(5);
  }
}

static inline void bootUiStep(const __FlashStringHelper* top, const __FlashStringHelper* bottom, unsigned long ms){
  bootUiStep(String(top), String(bottom), ms);
}

static inline uint8_t lcdTargetMaskFromLine(const String &line){
  // Single-display build: route everything to LCD1.
  (void)line;
  return LCD_TGT_1;
}

class LcdStatus {
public:
  void begin(const String &defaultMsg, unsigned long holdMs){
    _defaultMsg = defaultMsg;
    _holdMs = holdMs;
    _lastShowMs = 0;
    _last = "";
    show(defaultMsg, "", true);
  }

  void setPinned(bool pinned){
    _pinned = pinned;
    if (!_pinned){
      _lastShowMs = millis();
    }
  }

  bool isPinned() const { return _pinned; }

  // Force the next show*() call to redraw even when the cached content matches,
  // and physically clear the LCD so any stale pixels left by direct writers
  // (boot UI, raw library calls) are wiped before the next render.
  void invalidate(){
    _last = "";
    lcdHubFullClear(LCD_TGT_1);
  }

  void show(const String &top, const String &bottom = "", bool force=false){
    showTo(LCD_TGT_1, top, bottom, force);
  }

  void show(const __FlashStringHelper* top, const __FlashStringHelper* bottom = NULL, bool force = false){
    showTo(LCD_TGT_1, String(top), bottom ? String(bottom) : "", force);
  }

  void showTo(uint8_t targetMask, const String &top, const String &bottom = "", bool force=false){
    show4To(targetMask, top, bottom, String(""), String(""), force);
  }

  void show4To(uint8_t targetMask, const String &l1, const String &l2, const String &l3, const String &l4, bool force=false){
    if (!lcdHubAny()) return;
    if (_pinned && !force) return;

    // Forced calls (menu/state transitions) must always reach the LCD even if
    // the cached content matches, because direct/bypass writers (boot UI, raw
    // library calls) may have left stale pixels. Importantly, we also skip the
    // big String concatenation in this case so AVR doesn't run out of heap and
    // silently drop the render.
    if (force){
      _last = "";
      _lastShowMs = millis();
      lcdHubPrint4(targetMask, l1, l2, l3, l4);
      return;
    }

    String combined = l1;
    combined += '\n';
    combined += l2;
    combined += '\n';
    combined += l3;
    combined += '\n';
    combined += l4;
    if (combined == _last) return;
    _last = combined;
    _lastShowMs = millis();
    lcdHubPrint4(targetMask, l1, l2, l3, l4);
  }

  void tick(){
    if (!lcdHubAny()) return;
    if (_pinned) return;
    if (_holdMs == 0) return;
    if (_lastShowMs == 0) return;
    if (millis() - _lastShowMs < _holdMs) return;
    String def = _defaultMsg + "\n\n\n";
    if (_last == def) return;
    show(_defaultMsg, "", true);
  }

private:
  String _defaultMsg;
  String _last;
  unsigned long _holdMs{3000};
  unsigned long _lastShowMs{0};
  bool _pinned{false};
};

extern LcdStatus g_lcdStatus;

#else
static inline bool lcdHubAny(){ return false; }
static inline uint8_t lcdTargetMaskFromLine(const String &){ return LCD_TGT_1; }
#endif // LCD_ENABLED

#endif // SENTRY_APP_LCD_HUB_H
