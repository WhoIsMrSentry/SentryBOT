#ifndef ROBOT_NEOPIXEL_H
#define ROBOT_NEOPIXEL_H

// NeoPixel support removed — provide no-op stubs for compatibility.

inline void neopixel_begin() {}
inline void neopixel_tick() {}
inline void neopixel_stop() {}
inline void neopixel_start_animation(const String &name, int r, int g, int b, int iterations, unsigned int interval_ms) {}
inline void neopixel_set_pixels_from_line(const String &line) {}

#endif // ROBOT_NEOPIXEL_H
