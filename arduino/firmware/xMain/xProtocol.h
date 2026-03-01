#ifndef ROBOT_PROTOCOL_H
#define ROBOT_PROTOCOL_H

#include <Arduino.h>
#include "xConfig.h"

// Line-delimited JSON protocol (NDJSON).
// Each line is a JSON object, e.g.:
// {"cmd":"hello"}
// {"cmd":"set_servo","index":0,"deg":90}
// {"cmd":"set_pose","pose":[90,90,90,90,90,90,90,90],"duration_ms":1000}
// {"cmd":"leg_ik","x":120,"y":0,"side":"L"}
// {"cmd":"stepper","id":0,"mode":"pos","value":1000}
// {"cmd":"imu_cal"}
// Replies are also JSON lines with {"ok":true/...} or {"err":"..."}

struct ProtoIn {
  String raw; // the full line
};

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

  static void sendOk(const String &msg = "") {
    if (msg.length()) SERIAL_IO.println(String("{\"ok\":true,\"msg\":\"") + escape(msg) + "\"}");
    else SERIAL_IO.println(F("{\"ok\":true}"));
  }
  static void sendErr(const String &err) {
    SERIAL_IO.println(String("{\"ok\":false,\"err\":\"") + escape(err) + "\"}");
  }

  // Minimal JSON helper (escape only quotes and backslashes)
  static String escape(const String &s){
    String r; r.reserve(s.length()+8);
    for (size_t i=0;i<s.length();++i){
      char c=s[i];
      if (c=='"' || c=='\\') { r+='\\'; r+=c; }
      else if (c=='\n') { r+="\\n"; }
      else r+=c;
    }
    return r;
  }

private:
  static String buf;
};

// Note: `Protocol::buf` is declared in the class but must be defined
// in a single translation unit to avoid multiple-definition link errors.
// See xProtocol.cpp for the single-definition.

#endif // ROBOT_PROTOCOL_H