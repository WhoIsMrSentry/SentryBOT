#ifndef ROBOT_PROTOCOL_H
#define ROBOT_PROTOCOL_H

#include <Arduino.h>
#include <Wire.h>
#include <stdlib.h>
#if defined(ARDUINO_ARCH_AVR)
#include <avr/pgmspace.h>
#endif
#include "xConfig.h"

// Line-delimited JSON protocol (NDJSON).
// Each line is a JSON object, e.g.:
// {"cmd":"hello"}
// {"cmd":"set_servo","index":0,"deg":90}
// {"cmd":"set_pose","pose":[90,90,90,90],"duration_ms":1000}
// {"cmd":"stepper","id":0,"mode":"pos","value":1000}
// {"cmd":"imu_cal"}
// Replies are also JSON lines with {"ok":true,...} or {"ok":false,"err":"..."}

// Forward declaration so temperature alerts & cute sounds share one retry queue.
inline void emitNeopixelRequest(const String &name, const String &color = "", int iterations = 1);

class Protocol {
public:
  static bool readLine(Stream &s, String &out) {
    // Non-blocking line read (\n terminated)
    while (s.available()) {
      char c = (char)s.read();
      if (c == '\r') continue;
      if (c == '\n') { out = buf; buf = ""; return true; }
      buf += c;
      if (buf.length() > 256) { buf = ""; } // guard
    }
    return false;
  }

  // Request sequence tracking so every synchronous reply can echo "seq"
  static void setRequestSeq(bool hasSeq, long seq) {
    hasCurrentSeq = hasSeq;
    currentSeq = seq;
  }
  static void clearRequestSeq() {
    hasCurrentSeq = false;
    currentSeq = -1;
  }
  struct SeqScope {
    SeqScope(bool hasSeq, long seq) { setRequestSeq(hasSeq, seq); }
    ~SeqScope() { clearRequestSeq(); }
  };

  static void writeSeqSuffix(Stream &out = SERIAL_IO) {
    if (hasCurrentSeq) {
      out.print(F(",\"seq\":"));
      out.print(currentSeq);
    }
  }

  static void endJsonReply(Stream &out = SERIAL_IO) {
    writeSeqSuffix(out);
    out.println('}');
  }

  static void sendOk(const String &msg = "") {
    SERIAL_IO.print(F("{\"ok\":true"));
    if (msg.length()) {
      SERIAL_IO.print(F(",\"msg\":\""));
      printEscaped(SERIAL_IO, msg);
      SERIAL_IO.print('"');
    }
    endJsonReply(SERIAL_IO);
  }
  static void sendOk(const __FlashStringHelper *msg) {
    SERIAL_IO.print(F("{\"ok\":true"));
    if (msg) {
      SERIAL_IO.print(F(",\"msg\":\""));
      SERIAL_IO.print(msg);
      SERIAL_IO.print('"');
    }
    endJsonReply(SERIAL_IO);
  }
  static void sendErr(const String &err) {
    SERIAL_IO.print(F("{\"ok\":false,\"err\":\""));
    printEscaped(SERIAL_IO, err);
    SERIAL_IO.print('"');
    endJsonReply(SERIAL_IO);
  }
  static void sendErr(const __FlashStringHelper *err) {
    SERIAL_IO.print(F("{\"ok\":false,\"err\":\""));
    SERIAL_IO.print(err);
    SERIAL_IO.print('"');
    endJsonReply(SERIAL_IO);
  }

  static void printEscaped(Stream &out, const String &s){
    for (size_t i = 0; i < s.length(); ++i){
      char c = s[i];
      if (c=='"' || c=='\\') { out.print('\\'); out.print(c); }
      else if (c=='\n') out.print(F("\\n"));
      else if (c=='\r') out.print(F("\\r"));
      else if (c=='\t') out.print(F("\\t"));
      else out.print(c);
    }
  }

  // Flash-string JSON parsing helpers (zero SRAM key literals & no fixed index offsets)
  static int findKey(const String &line, const __FlashStringHelper *key, int startFrom = 0, int maxEnd = -1) {
    if (!key || startFrom < 0 || startFrom >= (int)line.length()) return -1;
    const char *base = line.c_str();
#if defined(ARDUINO_ARCH_AVR)
    const char *hit = strstr_P(base + startFrom, (PGM_P)key);
#else
    const char *hit = strstr(base + startFrom, reinterpret_cast<const char *>(key));
#endif
    if (!hit) return -1;
    int pos = (int)(hit - base);
    if (maxEnd >= 0 && pos >= maxEnd) return -1;
    return pos;
  }

  static bool hasKey(const String &line, const __FlashStringHelper *key, int startFrom = 0, int maxEnd = -1) {
    return findKey(line, key, startFrom, maxEnd) >= 0;
  }

  static size_t flashKeyLen(const __FlashStringHelper *key) {
#if defined(ARDUINO_ARCH_AVR)
    return strlen_P((PGM_P)key);
#else
    return strlen(reinterpret_cast<const char *>(key));
#endif
  }

  static long parseJsonLongAfter(const String &line, const __FlashStringHelper *key, long defaultVal, bool *found = nullptr, int startFrom = 0, int maxEnd = -1) {
    int p = findKey(line, key, startFrom, maxEnd);
    if (p < 0) { if (found) *found = false; return defaultVal; }
    p += (int)flashKeyLen(key);
    const char *s = line.c_str() + p;
    while (*s == ' ' || *s == '\t') s++;
    char *endp = nullptr;
    long v = strtol(s, &endp, 10);
    if (endp == s) { if (found) *found = false; return defaultVal; }
    if (found) *found = true;
    return v;
  }

  static float parseJsonFloatAfter(const String &line, const __FlashStringHelper *key, float defaultVal, bool *found = nullptr, int startFrom = 0, int maxEnd = -1) {
    int p = findKey(line, key, startFrom, maxEnd);
    if (p < 0) { if (found) *found = false; return defaultVal; }
    p += (int)flashKeyLen(key);
    const char *s = line.c_str() + p;
    while (*s == ' ' || *s == '\t') s++;
    char *endp = nullptr;
    double v = strtod(s, &endp);
    if (endp == s || !isfinite(v)) { if (found) *found = false; return defaultVal; }
    if (found) *found = true;
    return (float)v;
  }

  static bool parseJsonBoolAfter(const String &line, const __FlashStringHelper *key, bool defaultVal, bool *found = nullptr, int startFrom = 0, int maxEnd = -1) {
    int p = findKey(line, key, startFrom, maxEnd);
    if (p < 0) { if (found) *found = false; return defaultVal; }
    p += (int)flashKeyLen(key);
    const char *s = line.c_str() + p;
    while (*s == ' ' || *s == '\t') s++;
    if (strncmp(s, "true", 4) == 0) { if (found) *found = true; return true; }
    if (strncmp(s, "false", 5) == 0) { if (found) *found = true; return false; }
    if (found) *found = false;
    return defaultVal;
  }

  static String parseJsonStringAfter(const String &line, const __FlashStringHelper *key, int startFrom = 0, int maxEnd = -1) {
    int p = findKey(line, key, startFrom, maxEnd);
    if (p < 0) return "";
    p += (int)flashKeyLen(key);
    while (p < (int)line.length() && (line[p] == ' ' || line[p] == '\t')) p++;
    if (p >= (int)line.length() || line[p] != '"') return "";
    p++;
    int e = line.indexOf('"', p);
    if (e < p || (maxEnd >= 0 && e > maxEnd)) return "";
    return line.substring(p, e);
  }

  static bool findObjectBounds(const String &line, const __FlashStringHelper *key, int &objStart, int &objEnd) {
    int p = findKey(line, key);
    if (p < 0) return false;
    int brace = line.indexOf('{', p + (int)flashKeyLen(key));
    if (brace < 0) return false;
    int depth = 0;
    bool inStr = false;
    for (int i = brace; i < (int)line.length(); ++i) {
      char c = line[i];
      if (c == '"' && (i == 0 || line[i - 1] != '\\')) inStr = !inStr;
      if (inStr) continue;
      if (c == '{') depth++;
      else if (c == '}') {
        depth--;
        if (depth == 0) {
          objStart = brace;
          objEnd = i + 1;
          return true;
        }
      }
    }
    return false;
  }

  // I2C error & timeout counter reported in telemetry / get_state
  static void recordI2cError() { i2cErrors++; }
  static void recordWireStatus(uint8_t status) {
    if (status != 0) i2cErrors++;
    pollWireTimeout();
  }
  static void pollWireTimeout() {
#if defined(ARDUINO_ARCH_AVR) && defined(WIRE_HAS_TIMEOUT)
    if (Wire.getWireTimeoutFlag()) {
      Wire.clearWireTimeoutFlag();
      i2cErrors++;
    }
#endif
  }
  static uint32_t getI2cErrorCount() { return i2cErrors; }

private:
  static String buf;
  static long currentSeq;
  static bool hasCurrentSeq;
  static uint32_t i2cErrors;
};

// Keep backward-compatible wrapper accepting Flash or const char keys
static inline String parseJsonStringAfter(const String &line, const char *key){
  int p = line.indexOf(key);
  if (p < 0) return "";
  p += (int)strlen(key);
  int e = line.indexOf('"', p);
  if (e < p) return "";
  return line.substring(p, e);
}

// Note: `Protocol::buf` is declared in the class but must be defined
// in a single translation unit to avoid multiple-definition link errors.
// See xProtocol.cpp for the single-definition.

#endif // ROBOT_PROTOCOL_H