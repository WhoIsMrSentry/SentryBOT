#ifndef ROBOT_NEOPIXEL_H
#define ROBOT_NEOPIXEL_H

#include <Arduino.h>
#if NEOPIXEL_ENABLED
#include <Adafruit_NeoPixel.h>
#endif

#include "../xConfig.h"

#if NEOPIXEL_ENABLED
static Adafruit_NeoPixel _neo_strip = Adafruit_NeoPixel(NEO_NUM_LEDS, PIN_NEOPIXEL, NEO_GRB + NEO_KHZ800);

inline void neopixel_begin(){
  _neo_strip.begin();
  _neo_strip.show();
}

inline void neopixel_clear(){
  for (uint16_t i=0;i<NEO_NUM_LEDS;i++) _neo_strip.setPixelColor(i, 0);
  _neo_strip.show();
}

// --- simple animation engine state ---
enum NeoEffect { NE_OFF=0, NE_FILL, NE_RAINBOW, NE_THEATER, NE_BREATHE, NE_CLEAR };
static NeoEffect _neo_effect = NE_OFF;
static uint8_t _neo_r=255, _neo_g=255, _neo_b=255;
static int _neo_iter_target = 0; // 0 = infinite
static int _neo_iter_count = 0;
static unsigned long _neo_last_ms = 0;
static int _neo_step = 0;
static unsigned int _neo_interval_ms = 50;

// wheel helper (0-255 -> RGB)
inline uint32_t neo_wheel(uint8_t pos){
  if (pos < 85) return _neo_strip.Color(pos * 3, 255 - pos * 3, 0);
  if (pos < 170){ pos -= 85; return _neo_strip.Color(255 - pos * 3, 0, pos * 3); }
  pos -= 170; return _neo_strip.Color(0, pos * 3, 255 - pos * 3);
}

inline void neopixel_stop(){ _neo_effect = NE_OFF; }

inline void neopixel_start_animation(const String &name, int r, int g, int b, int iterations, unsigned int interval_ms){
  String n = name;
  n.toLowerCase();
  _neo_r = (uint8_t)constrain(r, 0, 255);
  _neo_g = (uint8_t)constrain(g, 0, 255);
  _neo_b = (uint8_t)constrain(b, 0, 255);
  _neo_iter_target = (iterations <= 0) ? 0 : iterations;
  _neo_iter_count = 0;
  _neo_step = 0;
  _neo_interval_ms = (interval_ms>0)?interval_ms:50;
  _neo_last_ms = millis();
  if (n == "fill") _neo_effect = NE_FILL;
  else if (n == "rainbow") _neo_effect = NE_RAINBOW;
  else if (n == "theater_chase" || n=="theater") _neo_effect = NE_THEATER;
  else if (n == "breathe" || n=="breathe_pulse" || n=="pulse") _neo_effect = NE_BREATHE;
  else if (n == "clear") _neo_effect = NE_CLEAR;
  else _neo_effect = NE_FILL; // fallback
}

inline void neopixel_tick(){
  if (_neo_effect == NE_OFF) return;
  unsigned long now = millis();
  if (now - _neo_last_ms < _neo_interval_ms) return;
  _neo_last_ms = now;

  if (_neo_effect == NE_FILL){
    for (uint16_t i=0;i<NEO_NUM_LEDS;i++) _neo_strip.setPixelColor(i, _neo_strip.Color(_neo_r,_neo_g,_neo_b));
    _neo_strip.show();
    if (_neo_iter_target){ _neo_iter_count++; if (_neo_iter_count>=_neo_iter_target) neopixel_stop(); }
    return;
  }

  if (_neo_effect == NE_CLEAR){ neopixel_clear(); neopixel_stop(); return; }

  if (_neo_effect == NE_RAINBOW){
    for (uint16_t i=0;i<NEO_NUM_LEDS;i++){
      uint8_t p = (uint8_t)((i * 256 / NEO_NUM_LEDS) + _neo_step);
      _neo_strip.setPixelColor(i, neo_wheel(p));
    }
    _neo_strip.show();
    _neo_step = (_neo_step + 1) & 0xFF;
    if (_neo_step == 0 && _neo_iter_target){ _neo_iter_count++; if (_neo_iter_count>=_neo_iter_target) neopixel_stop(); }
    return;
  }

  if (_neo_effect == NE_THEATER){
    int phase = _neo_step % 3;
    for (uint16_t i=0;i<NEO_NUM_LEDS;i++){
      if ((i + phase) % 3 == 0) _neo_strip.setPixelColor(i, _neo_strip.Color(_neo_r,_neo_g,_neo_b));
      else _neo_strip.setPixelColor(i, 0);
    }
    _neo_strip.show();
    _neo_step++;
    if (_neo_step % 3 == 0 && _neo_iter_target){ _neo_iter_count++; if (_neo_iter_count>=_neo_iter_target) neopixel_stop(); }
    return;
  }

  if (_neo_effect == NE_BREATHE){
    // simple triangular breathe
    int period = max(200, (int)_neo_interval_ms * 50); // rough control
    int t = _neo_step % period;
    float phase = (float)t / (float)period;
    float scale = (phase < 0.5f) ? (phase * 2.0f) : (2.0f - phase*2.0f);
    uint8_t rr = (uint8_t)( (float)_neo_r * scale );
    uint8_t gg = (uint8_t)( (float)_neo_g * scale );
    uint8_t bb = (uint8_t)( (float)_neo_b * scale );
    for (uint16_t i=0;i<NEO_NUM_LEDS;i++) _neo_strip.setPixelColor(i, _neo_strip.Color(rr,gg,bb));
    _neo_strip.show();
    _neo_step++;
    if (_neo_step % period == 0 && _neo_iter_target){ _neo_iter_count++; if (_neo_iter_count>=_neo_iter_target) neopixel_stop(); }
    return;
  }
}

// Parse a JSON line containing "pixels":[[r,g,b],...]
inline void neopixel_set_pixels_from_line(const String &line){
  int p = line.indexOf("\"pixels\"");
  if (p < 0) return;
  int lb = line.indexOf('[', p);
  if (lb < 0) return;
  // collect integers
  int vals[NEO_NUM_LEDS * 3];
  int vi = 0;
  bool in_number = false;
  long cur = 0;
  bool negative = false;
  for (int i = lb; i < line.length() && vi < NEO_NUM_LEDS*3; ++i){
    char c = line.charAt(i);
    if (c == '-') { negative = true; in_number = true; cur = 0; continue; }
    if (c >= '0' && c <= '9'){
      in_number = true;
      cur = cur * 10 + (c - '0');
    } else {
      if (in_number){
        int v = negative ? -(int)cur : (int)cur;
        if (v < 0) v = 0;
        if (v > 255) v = 255;
        vals[vi++] = v;
      }
      in_number = false;
      cur = 0;
      negative = false;
    }
  }
  // apply values as RGB triplets
  int pix = 0;
  for (int i=0;i+2<vi && pix < NEO_NUM_LEDS; i += 3){
    int r = vals[i];
    int g = vals[i+1];
    int b = vals[i+2];
    _neo_strip.setPixelColor(pix++, _neo_strip.Color(r, g, b));
  }
  // if fewer specified than strip length, clear remaining
  for (int j=pix;j<NEO_NUM_LEDS;j++) _neo_strip.setPixelColor(j, 0);
  _neo_strip.show();
}

#endif // NEOPIXEL_ENABLED

#endif // ROBOT_NEOPIXEL_H
