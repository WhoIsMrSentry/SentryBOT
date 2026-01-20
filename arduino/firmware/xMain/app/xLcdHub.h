#ifndef SENTRY_APP_LCD_HUB_H
#define SENTRY_APP_LCD_HUB_H

#include <Arduino.h>
#include "../xConfig.h"

#if LCD_ENABLED
#include <Wire.h>
#include "../xPeripherals.h"

// Shared LCD hub routing constants.
static constexpr uint8_t LCD_TGT_1 = 0x01;
static constexpr uint8_t LCD_TGT_2 = 0x02;
static constexpr uint8_t LCD_TGT_BOTH = (LCD_TGT_1 | LCD_TGT_2);

// Globals owned by xMain.ino
extern LcdDisplay g_lcd1;
extern bool g_lcd1Ok;
extern uint8_t g_lcdRouteMask;

#if LCD2_ENABLED
extern LcdDisplay g_lcd2;
extern bool g_lcd2Ok;
#endif

static inline bool i2cDevicePresent(uint8_t addr){
  Wire.beginTransmission(addr);
  return (Wire.endTransmission() == 0);
}

static inline void bootInfo(const char *name, bool ok){
  SERIAL_IO.print(F("{\"info\":\"boot_check\",\"name\":\""));
  SERIAL_IO.print(name);
  SERIAL_IO.print(F("\",\"ok\":"));
  SERIAL_IO.print(ok ? F("true") : F("false"));
  SERIAL_IO.println(F("}"));
}

static inline uint8_t lcdHubAvailableMask(){
  uint8_t m = 0;
  if (g_lcd1Ok) m |= LCD_TGT_1;
#if LCD2_ENABLED
  if (g_lcd2Ok) m |= LCD_TGT_2;
#endif
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

static inline void lcdHubPrint(uint8_t requestedMask, const String &top, const String &bottom){
  uint8_t m = lcdHubResolveMask(requestedMask);
  if ((m & LCD_TGT_1) && g_lcd1Ok) g_lcd1.printLines(top, bottom);
#if LCD2_ENABLED
  if ((m & LCD_TGT_2) && g_lcd2Ok) g_lcd2.printLines(top, bottom);
#endif
}

static inline void lcdHubPrintDefault(const String &top, const String &bottom){
  lcdHubPrint(g_lcdRouteMask, top, bottom);
}

static inline void bootUiStep(const String &top, const String &bottom, unsigned long ms){
  if (!BOOT_UI_ENABLED) return;
  if (!lcdHubAny()) return;

  lcdHubPrintDefault(top, bottom);

  unsigned long t0 = millis();
  while (millis() - t0 < ms){
    // keep system responsive enough during boot UI
    if (SERIAL_IO.available()){
      // allow host to break long boot screens by sending any byte
      SERIAL_IO.read();
      break;
    }
    delay(5);
  }
}

static inline int parseJsonIntAfter(const String &line, const char *key, int defaultVal, bool *found=nullptr){
  int p = line.indexOf(key);
  if (p < 0){ if (found) *found = false; return defaultVal; }
  if (found) *found = true;
  p += (int)strlen(key);
  while (p < (int)line.length() && (line[p] == ' ')) p++;
  bool neg = false;
  if (p < (int)line.length() && line[p] == '-') { neg = true; p++; }
  long v = 0;
  bool any = false;
  while (p < (int)line.length()){
    char c = line[p];
    if (c < '0' || c > '9') break;
    any = true;
    v = (v * 10) + (c - '0');
    p++;
  }
  if (!any) return defaultVal;
  return neg ? (int)(-v) : (int)v;
}

static inline String parseJsonStringAfter(const String &line, const char *key){
  int p = line.indexOf(key);
  if (p < 0) return "";
  p += (int)strlen(key);
  int e = line.indexOf('"', p);
  if (e <= p) return "";
  return line.substring(p, e);
}

static inline uint8_t lcdTargetMaskFromLine(const String &line){
  // Priority: explicit numeric id, then string target.
  bool foundId = false;
  int id = parseJsonIntAfter(line, "\"id\":", 0, &foundId);
  if (foundId){
    if (id == 1) return LCD_TGT_1;
    if (id == 2) return LCD_TGT_2;
    return LCD_TGT_BOTH;
  }

  String t = parseJsonStringAfter(line, "\"target\":\"");
  t.toLowerCase();
  if (t == "1" || t == "lcd1") return LCD_TGT_1;
  if (t == "2" || t == "lcd2") return LCD_TGT_2;
  if (t == "both" || t == "all") return LCD_TGT_BOTH;
  return g_lcdRouteMask;
}

class LcdStatus {
public:
  void begin(const String &defaultMsg, unsigned long holdMs){
    _defaultMsg = defaultMsg;
    _holdMs = holdMs;
    _lastShowMs = 0;
    _lastTop = "";
    _lastBottom = "";
    show(defaultMsg, "", true);
  }

  void setPinned(bool pinned){
    _pinned = pinned;
    if (!_pinned){
      // Reset timer so we don't instantly revert right after unpin.
      _lastShowMs = millis();
    }
  }

  bool isPinned() const { return _pinned; }

  void show(const String &top, const String &bottom = "", bool force=false){
    if (!lcdHubAny()) return;
    if (_pinned && !force) return;
    if (top == _lastTop && bottom == _lastBottom) return; // Ignore even if forced if content is identical
    _lastTop = top;
    _lastBottom = bottom;
    _lastShowMs = millis();
    lcdHubPrintDefault(top, bottom);
  }

  void showTo(uint8_t targetMask, const String &top, const String &bottom = "", bool force=false){
    if (!lcdHubAny()) return;
    if (_pinned && !force) return;
    if (top == _lastTop && bottom == _lastBottom){
      // Content same; if forced we might still want to ensure it's on this specific display,
      // but to solve flicker we avoid redundant print calls.
      return;
    }
    _lastTop = top;
    _lastBottom = bottom;
    _lastShowMs = millis();
    lcdHubPrint(targetMask, top, bottom);
  }

  void tick(){
    if (!lcdHubAny()) return;
    if (_pinned) return;
    if (_holdMs == 0) return;
    if (_lastShowMs == 0) return;
    if (millis() - _lastShowMs < _holdMs) return;
    if (_lastTop == _defaultMsg && _lastBottom.length() == 0) return;
    show(_defaultMsg, "", true);
  }

private:
  String _defaultMsg;
  String _lastTop;
  String _lastBottom;
  unsigned long _holdMs{3000};
  unsigned long _lastShowMs{0};
  bool _pinned{false};
};

extern LcdStatus g_lcdStatus;

#endif // LCD_ENABLED

#endif // SENTRY_APP_LCD_HUB_H
