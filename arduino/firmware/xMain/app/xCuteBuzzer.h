#ifndef SENTRY_APP_CUTE_BUZZER_H
#define SENTRY_APP_CUTE_BUZZER_H

#include <Arduino.h>
#include "../xConfig.h"
#include "../xProtocol.h"

enum CuteSoundKey : uint8_t {
  CUTE_CONNECTION = 0,
  CUTE_DISCONNECTION,
  CUTE_BUTTON_PUSHED,
  CUTE_MODE1,
  CUTE_MODE2,
  CUTE_MODE3,
  CUTE_HAPPY,
  CUTE_HAPPY_SHORT,
  CUTE_SUPER_HAPPY,
  CUTE_SAD,
  CUTE_SURPRISE,
  CUTE_OHOOH,
  CUTE_OHOOH2,
  CUTE_CUDDLY,
  CUTE_CONFUSED,
  CUTE_SLEEPING,
  CUTE_FART1,
  CUTE_FART2,
  CUTE_FART3,
  CUTE_JUMP,
};

#if BUZZER_ENABLED
#include "../xPeripherals.h"

extern BuzzerPair g_buzzer;
extern BuzzerSongPlayer g_song;
extern BuzzerOut g_buzzerDefaultOut;
extern bool g_buzzerBothEnabled;
extern uint16_t g_buzzerFreqLoud;
extern uint16_t g_buzzerFreqQuiet;

// Optional external library controlled by config.
#if defined(CUTE_BUZZER_LIB_ENABLED) && CUTE_BUZZER_LIB_ENABLED
#include <CuteBuzzerSounds.h>
#define SENTRY_CUTE_BUZZER_LIB 1
#else
#define SENTRY_CUTE_BUZZER_LIB 0
#endif

// Forward declarations for inline helpers (declared later in this header)
static inline void enqueueNeopixelPending(uint16_t seq, const String &payload);
static inline void markNeopixelAck(uint16_t seq);
static inline void neopixelTick();

static inline void emitNeopixelRequest(const String &name, const String &color = "", int iterations = 1){
  // Validate iterations and color to avoid malformed or harmful values
  const int MAX_ITER = 10;
  if (iterations < 1) iterations = 1;
  if (iterations > MAX_ITER) iterations = MAX_ITER;
  // basic color format check: either empty or R,G,B where 0<=x<=255
  auto isValidColor = [](const String &c)->bool{
    if (c.length()==0) return true;
    int parts = 0; int last = 0;
    for (int i=0;i<=c.length();++i){
      if (i==c.length() || c[i]==','){
        String tok = c.substring(last, i);
        tok.trim();
        if (tok.length()==0) return false;
        int v = tok.toInt();
        if (v < 0 || v > 255) return false;
        parts++; last = i+1;
      }
    }
    return parts==3;
  };

  if (!isValidColor(color)){
    // If invalid color, clear it so Pi uses default behavior
  }

  // Build payload once and enqueue for retry management (seq assigned by helper)
  static uint16_t g_neopixel_seq = 1;
  uint16_t seq = g_neopixel_seq++;
  if (g_neopixel_seq == 0) g_neopixel_seq = 1; // avoid zero

  String payload = String("{\"ok\":true,\"event\":\"neopixel_request\",\"name\":\"") + Protocol::escape(name) + "\"";
  if (color.length()>0 && isValidColor(color)){
    payload += String(",\"color\":\"") + Protocol::escape(color) + "\"";
  }
  payload += String(",\"iterations\":") + String(iterations);
  payload += String(",\"seq\":") + String(seq);
  payload += "}";

  // Enqueue pending payload for the retry engine (inline implementation below)
  enqueueNeopixelPending(seq, payload);

  SERIAL_IO.println(payload);
}

static inline void emitCutePlayed(const String &name){
  String evt = String("{\"ok\":true,\"event\":\"cute_sound\",\"name\":\"") + Protocol::escape(name) + "\"}";
  SERIAL_IO.println(evt);
}

static inline uint8_t activeBuzzerPin(){
  return (g_buzzerDefaultOut == BUZZER_OUT_LOUD) ? (uint8_t)BUZZER_LOUD_PIN : (uint8_t)BUZZER_QUIET_PIN;
}

static inline const char* cuteName(CuteSoundKey key){
  // Use PROGMEM on AVR to save RAM
#if defined(ARDUINO_ARCH_AVR)
  static const char names[][16] PROGMEM = {
    "connection","disconnection","button_pushed","mode1",
    "mode2","mode3","happy","happy_short",
    "super_happy","sad","surprise","ohooh",
    "ohooh2","cuddly","confused","sleeping",
    "fart1","fart2","fart3","jump"
  };
  static char buf[24];
  if ((int)key >= 0 && (int)key < 20){
    strcpy_P(buf, (PGM_P)names[key]);
    return buf;
  }
  return "unknown";
#else
  switch (key){
    case CUTE_CONNECTION: return "connection";
    case CUTE_DISCONNECTION: return "disconnection";
    case CUTE_BUTTON_PUSHED: return "button_pushed";
    case CUTE_MODE1: return "mode1";
    case CUTE_MODE2: return "mode2";
    case CUTE_MODE3: return "mode3";
    case CUTE_HAPPY: return "happy";
    case CUTE_HAPPY_SHORT: return "happy_short";
    case CUTE_SUPER_HAPPY: return "super_happy";
    case CUTE_SAD: return "sad";
    case CUTE_SURPRISE: return "surprise";
    case CUTE_OHOOH: return "ohooh";
    case CUTE_OHOOH2: return "ohooh2";
    case CUTE_CUDDLY: return "cuddly";
    case CUTE_CONFUSED: return "confused";
    case CUTE_SLEEPING: return "sleeping";
    case CUTE_FART1: return "fart1";
    case CUTE_FART2: return "fart2";
    case CUTE_FART3: return "fart3";
    case CUTE_JUMP: return "jump";
    default: return "unknown";
  }
#endif
}

static inline const char* cuteMenuLabel(CuteSoundKey key){
  // Use PROGMEM for menu labels on AVR
#if defined(ARDUINO_ARCH_AVR)
  static const char labels[][16] PROGMEM = {
    "CUTE CONNECT","CUTE DISCON","CUTE BUTTON","CUTE MODE1",
    "CUTE MODE2","CUTE MODE3","CUTE HAPPY","CUTE H-SHORT",
    "CUTE S-HAPPY","CUTE SAD","CUTE SURPRISE","CUTE OHOOH",
    "CUTE OHOOH2","CUTE CUDDLY","CUTE CONFUSE","CUTE SLEEP",
    "CUTE FART1","CUTE FART2","CUTE FART3","CUTE JUMP"
  };
  static char buf2[20];
  if ((int)key >= 0 && (int)key < 20){
    strcpy_P(buf2, (PGM_P)labels[key]);
    return buf2;
  }
  return "CUTE";
#else
  switch (key){
    case CUTE_CONNECTION: return "CUTE CONNECT";
    case CUTE_DISCONNECTION: return "CUTE DISCON";
    case CUTE_BUTTON_PUSHED: return "CUTE BUTTON";
    case CUTE_MODE1: return "CUTE MODE1";
    case CUTE_MODE2: return "CUTE MODE2";
    case CUTE_MODE3: return "CUTE MODE3";
    case CUTE_HAPPY: return "CUTE HAPPY";
    case CUTE_HAPPY_SHORT: return "CUTE H-SHORT";
    case CUTE_SUPER_HAPPY: return "CUTE S-HAPPY";
    case CUTE_SAD: return "CUTE SAD";
    case CUTE_SURPRISE: return "CUTE SURPRISE";
    case CUTE_OHOOH: return "CUTE OHOOH";
    case CUTE_OHOOH2: return "CUTE OHOOH2";
    case CUTE_CUDDLY: return "CUTE CUDDLY";
    case CUTE_CONFUSED: return "CUTE CONFUSE";
    case CUTE_SLEEPING: return "CUTE SLEEP";
    case CUTE_FART1: return "CUTE FART1";
    case CUTE_FART2: return "CUTE FART2";
    case CUTE_FART3: return "CUTE FART3";
    case CUTE_JUMP: return "CUTE JUMP";
    default: return "CUTE";
  }
#endif
}

static inline void cuteNeopixelFor(CuteSoundKey key){
  switch (key){
    case CUTE_CONNECTION: emitNeopixelRequest("PULSE", "0,180,80", 1); break;
    case CUTE_DISCONNECTION: emitNeopixelRequest("THEATER_CHASE", "220,30,30", 1); break;
    case CUTE_BUTTON_PUSHED: emitNeopixelRequest("PULSE", "180,180,180", 1); break;
    case CUTE_MODE1: emitNeopixelRequest("WAVE", "0,180,255", 1); break;
    case CUTE_MODE2: emitNeopixelRequest("WAVE", "180,0,255", 1); break;
    case CUTE_MODE3: emitNeopixelRequest("WAVE", "255,80,0", 1); break;
    case CUTE_HAPPY: emitNeopixelRequest("WAVE", "255,220,0", 2); break;
    case CUTE_HAPPY_SHORT: emitNeopixelRequest("PULSE", "255,220,0", 1); break;
    case CUTE_SUPER_HAPPY: emitNeopixelRequest("RAINBOW", "", 1); break;
    case CUTE_SAD: emitNeopixelRequest("BREATHE", "0,70,255", 2); break;
    case CUTE_SURPRISE: emitNeopixelRequest("TWINKLE", "255,255,255", 2); break;
    case CUTE_OHOOH: emitNeopixelRequest("THEATER_CHASE", "255,255,255", 1); break;
    case CUTE_OHOOH2: emitNeopixelRequest("THEATER_CHASE", "255,255,255", 2); break;
    case CUTE_CUDDLY: emitNeopixelRequest("BREATHE", "255,50,150", 2); break;
    case CUTE_CONFUSED: emitNeopixelRequest("PULSE", "170,0,255", 2); break;
    case CUTE_SLEEPING: emitNeopixelRequest("BREATHE", "20,40,120", 2); break;
    case CUTE_FART1: emitNeopixelRequest("ALTERNATING", "20,180,20", 2); break;
    case CUTE_FART2: emitNeopixelRequest("ALTERNATING", "40,220,40", 2); break;
    case CUTE_FART3: emitNeopixelRequest("ALTERNATING", "10,120,10", 2); break;
    case CUTE_JUMP: emitNeopixelRequest("COMET", "255,255,255", 2); break;
    default: break;
  }
}

static inline void cuteBuzzerInit(){
#if SENTRY_CUTE_BUZZER_LIB
  cute.init(activeBuzzerPin());
#endif
}

static inline void playCuteSound(CuteSoundKey key, bool emitNeopixel = true){
  const char *name = cuteName(key);
#if SENTRY_CUTE_BUZZER_LIB
  switch (key){
    case CUTE_CONNECTION: cute.play(S_CONNECTION); break;
    case CUTE_DISCONNECTION: cute.play(S_DISCONNECTION); break;
    case CUTE_BUTTON_PUSHED: cute.play(S_BUTTON_PUSHED); break;
    case CUTE_MODE1: cute.play(S_MODE1); break;
    case CUTE_MODE2: cute.play(S_MODE2); break;
    case CUTE_MODE3: cute.play(S_MODE3); break;
    case CUTE_HAPPY: cute.play(S_HAPPY); break;
    case CUTE_HAPPY_SHORT: cute.play(S_HAPPY_SHORT); break;
    case CUTE_SUPER_HAPPY: cute.play(S_SUPER_HAPPY); break;
    case CUTE_SAD: cute.play(S_SAD); break;
    case CUTE_SURPRISE: cute.play(S_SURPRISE); break;
    case CUTE_OHOOH: cute.play(S_OHOOH); break;
    case CUTE_OHOOH2: cute.play(S_OHOOH2); break;
    case CUTE_CUDDLY: cute.play(S_CUDDLY); break;
    case CUTE_CONFUSED: cute.play(S_CONFUSED); break;
    case CUTE_SLEEPING: cute.play(S_SLEEPING); break;
    case CUTE_FART1: cute.play(S_FART1); break;
    case CUTE_FART2: cute.play(S_FART2); break;
    case CUTE_FART3: cute.play(S_FART3); break;
    case CUTE_JUMP: cute.play(S_JUMP); break;
    default: break;
  }
#else
  uint16_t f = (g_buzzerDefaultOut == BUZZER_OUT_LOUD) ? g_buzzerFreqLoud : g_buzzerFreqQuiet;
  switch (key){
    case CUTE_CONNECTION: g_buzzer.beepOn(g_buzzerDefaultOut, f, 120); break;
    case CUTE_DISCONNECTION: g_buzzer.beepOn(g_buzzerDefaultOut, 450, 180); break;
    case CUTE_BUTTON_PUSHED: g_buzzer.beepOn(g_buzzerDefaultOut, f, 50); break;
    case CUTE_MODE1: g_buzzer.beepOn(g_buzzerDefaultOut, 1000, 100); break;
    case CUTE_MODE2: g_buzzer.beepOn(g_buzzerDefaultOut, 1400, 100); break;
    case CUTE_MODE3: g_buzzer.beepOn(g_buzzerDefaultOut, 1800, 100); break;
    case CUTE_HAPPY: g_song.play("bb8_1", g_buzzerDefaultOut); break;
    case CUTE_HAPPY_SHORT: g_buzzer.beepOn(g_buzzerDefaultOut, 1800, 80); break;
    case CUTE_SUPER_HAPPY: g_song.play("bb8_3", g_buzzerDefaultOut); break;
    case CUTE_SAD: g_buzzer.beepOn(g_buzzerDefaultOut, 320, 220); break;
    case CUTE_SURPRISE: g_buzzer.beepOn(g_buzzerDefaultOut, 2000, 80); break;
    case CUTE_OHOOH: g_buzzer.beepOn(g_buzzerDefaultOut, 900, 180); break;
    case CUTE_OHOOH2: g_buzzer.beepOn(g_buzzerDefaultOut, 1050, 220); break;
    case CUTE_CUDDLY: g_buzzer.beepOn(g_buzzerDefaultOut, 700, 180); break;
    case CUTE_CONFUSED: g_buzzer.beepOn(g_buzzerDefaultOut, 900, 120); break;
    case CUTE_SLEEPING: g_buzzer.beepOn(g_buzzerDefaultOut, 260, 260); break;
    case CUTE_FART1: g_buzzer.beepOn(g_buzzerDefaultOut, 220, 200); break;
    case CUTE_FART2: g_buzzer.beepOn(g_buzzerDefaultOut, 180, 220); break;
    case CUTE_FART3: g_buzzer.beepOn(g_buzzerDefaultOut, 140, 260); break;
    case CUTE_JUMP: g_buzzer.beepOn(g_buzzerDefaultOut, 2000, 120); break;
    default: break;
  }
#endif
  emitCutePlayed(String(name));
  if (emitNeopixel) cuteNeopixelFor(key);
}

// Mark a pending neopixel seq as acknowledged by Pi
// Retry/ack helpers implemented inline to ensure availability during AVR link
static const int _CUTE_PENDING_MAX = 6;
struct _CutePendingItem { uint16_t seq; String payload; uint8_t retries; unsigned long lastMs; bool done; };
static _CutePendingItem _g_cute_pending[_CUTE_PENDING_MAX] = {};

static inline void enqueueNeopixelPending(uint16_t seq, const String &payload){
  for (int i=0;i<_CUTE_PENDING_MAX;i++){
    if (_g_cute_pending[i].done || _g_cute_pending[i].seq==0){
      _g_cute_pending[i].seq = seq;
      _g_cute_pending[i].payload = payload;
      _g_cute_pending[i].retries = 0;
      _g_cute_pending[i].lastMs = millis();
      _g_cute_pending[i].done = false;
      return;
    }
  }
  int oldest = 0; unsigned long oldestMs = _g_cute_pending[0].lastMs;
  for (int i=1;i<_CUTE_PENDING_MAX;i++) if (_g_cute_pending[i].lastMs < oldestMs){ oldest = i; oldestMs = _g_cute_pending[i].lastMs; }
  _g_cute_pending[oldest].seq = seq;
  _g_cute_pending[oldest].payload = payload;
  _g_cute_pending[oldest].retries = 0;
  _g_cute_pending[oldest].lastMs = millis();
  _g_cute_pending[oldest].done = false;
}

static inline void markNeopixelAck(uint16_t seq){
  if (seq==0) return;
  for (int i=0;i<_CUTE_PENDING_MAX;i++){
    if (!_g_cute_pending[i].done && _g_cute_pending[i].seq == seq){
      _g_cute_pending[i].done = true;
      _g_cute_pending[i].seq = 0;
      _g_cute_pending[i].payload = String("");
      _g_cute_pending[i].retries = 0;
      _g_cute_pending[i].lastMs = 0;
      return;
    }
  }
}

static inline void neopixelTick(){
  const uint8_t MAX_RETRIES = 3;
  const unsigned long RETRY_MS = 600UL;
  unsigned long now = millis();
  for (int i=0;i<_CUTE_PENDING_MAX;i++){
    if (_g_cute_pending[i].done || _g_cute_pending[i].seq==0) continue;
    unsigned long elapsed = (now - _g_cute_pending[i].lastMs);
    if (_g_cute_pending[i].retries < MAX_RETRIES && elapsed >= RETRY_MS * (_g_cute_pending[i].retries + 1)){
      SERIAL_IO.println(_g_cute_pending[i].payload);
      _g_cute_pending[i].retries++;
      _g_cute_pending[i].lastMs = now;
    } else if (_g_cute_pending[i].retries >= MAX_RETRIES){
      _g_cute_pending[i].done = true;
    }
  }
}

static inline bool playCuteSoundByName(const String &name, bool emitNeopixel = true){
  String n = name;
  n.toLowerCase();
  if (n == "connection") { playCuteSound(CUTE_CONNECTION, emitNeopixel); return true; }
  if (n == "disconnection" || n == "disconnect") { playCuteSound(CUTE_DISCONNECTION, emitNeopixel); return true; }
  if (n == "button_pushed" || n == "button") { playCuteSound(CUTE_BUTTON_PUSHED, emitNeopixel); return true; }
  if (n == "mode1") { playCuteSound(CUTE_MODE1, emitNeopixel); return true; }
  if (n == "mode2") { playCuteSound(CUTE_MODE2, emitNeopixel); return true; }
  if (n == "mode3") { playCuteSound(CUTE_MODE3, emitNeopixel); return true; }
  if (n == "happy") { playCuteSound(CUTE_HAPPY, emitNeopixel); return true; }
  if (n == "happy_short") { playCuteSound(CUTE_HAPPY_SHORT, emitNeopixel); return true; }
  if (n == "super_happy" || n == "superhappy") { playCuteSound(CUTE_SUPER_HAPPY, emitNeopixel); return true; }
  if (n == "sad") { playCuteSound(CUTE_SAD, emitNeopixel); return true; }
  if (n == "surprise") { playCuteSound(CUTE_SURPRISE, emitNeopixel); return true; }
  if (n == "ohooh") { playCuteSound(CUTE_OHOOH, emitNeopixel); return true; }
  if (n == "ohooh2") { playCuteSound(CUTE_OHOOH2, emitNeopixel); return true; }
  if (n == "cuddly") { playCuteSound(CUTE_CUDDLY, emitNeopixel); return true; }
  if (n == "confused") { playCuteSound(CUTE_CONFUSED, emitNeopixel); return true; }
  if (n == "sleeping" || n == "sleep") { playCuteSound(CUTE_SLEEPING, emitNeopixel); return true; }
  if (n == "fart1") { playCuteSound(CUTE_FART1, emitNeopixel); return true; }
  if (n == "fart2") { playCuteSound(CUTE_FART2, emitNeopixel); return true; }
  if (n == "fart3") { playCuteSound(CUTE_FART3, emitNeopixel); return true; }
  if (n == "jump") { playCuteSound(CUTE_JUMP, emitNeopixel); return true; }
  return false;
}

#else
static inline void emitNeopixelRequest(const String &, const String & = "", int = 1){}
static inline void emitCutePlayed(const String &){}
static inline void cuteBuzzerInit(){}
static inline void playCuteSound(CuteSoundKey, bool = true){}
static inline bool playCuteSoundByName(const String &, bool = true){ return false; }
#endif

#endif // SENTRY_APP_CUTE_BUZZER_H