// --- Gerekli Kütüphaneler ---
#include <Adafruit_NeoPixel.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"

// --- ESP32 DEVKIT V1 İÇİN UYUMLU PIN TANIMLAMALARI ---
#define LED_PIN       21  // NeoPixel Veri Pini
#define LED_COUNT     23  // LED Sayısı (Bu sizin donanımınıza bağlı)

// --- Global Değişkenler ve Tanımlar ---
Adafruit_NeoPixel strip(LED_COUNT, LED_PIN, NEO_GRB + NEO_KHZ800);

// Seri Komut Kuyruğu
#define MAX_COMMANDS 30
#define MAX_COMMAND_LENGTH 128
String commandQueue[MAX_COMMANDS];
int commandQueueHead = 0;
int commandQueueTail = 0;
unsigned long lastCommandTime = 0;
bool commandProcessed = true;

// Seri Tampon Yönetimi
#define SERIAL_THROTTLE_TIME 5
unsigned long lastSerialCheck = 0;
int serialErrorCount = 0;
#define MAX_SERIAL_ERRORS 5

// --- FreeRTOS Tanımlamaları ---
TaskHandle_t animationTaskHandle = NULL;
QueueHandle_t animationCommandQueue;
SemaphoreHandle_t stripMutex; // NeoPixel şeridine erişim için mutex

// Animasyon komut yapısı
typedef struct {
    char name[24];
    char segment[16];
    uint32_t color1;
    uint32_t color2;
    int repeat;
} AnimationCommand;

volatile bool g_abortAnimation = false;
volatile bool g_preserveStaticPixels = false;
int g_segStart = 0;
int g_segEnd = LED_COUNT;

void segmentRange(const char* seg, int &startIdx, int &endIdx) {
    if (!seg || seg[0] == '\0') {
        startIdx = 0;
        endIdx = LED_COUNT;
        return;
    }
    if (strcasecmp(seg, "JEWEL") == 0 || strcasecmp(seg, "HEAD") == 0) {
        startIdx = 0;
        endIdx = min(7, LED_COUNT);
    } else if (strcasecmp(seg, "STICK_LEFT") == 0 || strcasecmp(seg, "LEFT_BROW") == 0) {
        startIdx = min(7, LED_COUNT);
        endIdx = min(15, LED_COUNT);
    } else if (strcasecmp(seg, "STICK_RIGHT") == 0 || strcasecmp(seg, "RIGHT_BROW") == 0) {
        startIdx = min(15, LED_COUNT);
        endIdx = LED_COUNT;
    } else if (strcasecmp(seg, "STICK") == 0 || strcasecmp(seg, "BODY") == 0) {
        startIdx = min(7, LED_COUNT);
        endIdx = LED_COUNT;
    } else {
        startIdx = 0;
        endIdx = LED_COUNT;
    }
}

bool shouldAbortAnimation() {
    return g_abortAnimation || hasCommand();
}

bool delayOrAbort(unsigned long ms) {
    unsigned long elapsed = 0;
    while (elapsed < ms) {
        if (shouldAbortAnimation()) return true;
        unsigned long chunk = min(15UL, ms - elapsed);
        vTaskDelay(pdMS_TO_TICKS(chunk));
        elapsed += chunk;
    }
    return shouldAbortAnimation();
}

// --- Renk Tanımlamaları ---
#define COLOR_RED     strip.Color(255, 0, 0)
#define COLOR_GREEN   strip.Color(0, 255, 0)
#define COLOR_BLUE    strip.Color(0, 0, 255)
#define COLOR_YELLOW  strip.Color(255, 255, 0)
#define COLOR_PURPLE  strip.Color(255, 0, 255)
#define COLOR_CYAN    strip.Color(0, 255, 255)
#define COLOR_WHITE   strip.Color(255, 255, 255)
#define COLOR_ORANGE  strip.Color(255, 165, 0)
#define COLOR_PINK    strip.Color(255, 105, 180)
#define COLOR_GOLD    strip.Color(255, 215, 0)
#define COLOR_TEAL    strip.Color(0, 128, 128)
#define COLOR_MAGENTA strip.Color(255, 0, 127)
#define COLOR_LIME    strip.Color(50, 205, 50)
#define COLOR_SKY_BLUE strip.Color(135, 206, 235)
#define COLOR_NAVY    strip.Color(0, 0, 128)
#define COLOR_MAROON  strip.Color(128, 0, 0)
#define COLOR_AQUA    strip.Color(127, 255, 212)
#define COLOR_VIOLET  strip.Color(138, 43, 226)
#define COLOR_CORAL   strip.Color(255, 127, 80)
#define COLOR_TURQUOISE strip.Color(64, 224, 208)
#define COLOR_BLACK   strip.Color(0, 0, 0)

// --- Yardımcı Fonksiyonlar ---

// İsimden Renk Alma (büyük/küçük harf duyarsız)
uint32_t getColorFromString(const char* colorName) {
  if (!colorName || strlen(colorName) == 0) return 0;
  if (strcasecmp(colorName, "RED") == 0) return COLOR_RED;
  else if (strcasecmp(colorName, "GREEN") == 0) return COLOR_GREEN;
  else if (strcasecmp(colorName, "BLUE") == 0) return COLOR_BLUE;
  else if (strcasecmp(colorName, "YELLOW") == 0) return COLOR_YELLOW;
  else if (strcasecmp(colorName, "PURPLE") == 0) return COLOR_PURPLE;
  else if (strcasecmp(colorName, "CYAN") == 0) return COLOR_CYAN;
  else if (strcasecmp(colorName, "WHITE") == 0) return COLOR_WHITE;
  else if (strcasecmp(colorName, "ORANGE") == 0) return COLOR_ORANGE;
  else if (strcasecmp(colorName, "PINK") == 0) return COLOR_PINK;
  else if (strcasecmp(colorName, "GOLD") == 0) return COLOR_GOLD;
  else if (strcasecmp(colorName, "TEAL") == 0) return COLOR_TEAL;
  else if (strcasecmp(colorName, "MAGENTA") == 0) return COLOR_MAGENTA;
  else if (strcasecmp(colorName, "LIME") == 0) return COLOR_LIME;
  else if (strcasecmp(colorName, "SKY_BLUE") == 0) return COLOR_SKY_BLUE;
  else if (strcasecmp(colorName, "NAVY") == 0) return COLOR_NAVY;
  else if (strcasecmp(colorName, "MAROON") == 0) return COLOR_MAROON;
  else if (strcasecmp(colorName, "AQUA") == 0) return COLOR_AQUA;
  else if (strcasecmp(colorName, "VIOLET") == 0) return COLOR_VIOLET;
  else if (strcasecmp(colorName, "CORAL") == 0) return COLOR_CORAL;
  else if (strcasecmp(colorName, "TURQUOISE") == 0) return COLOR_TURQUOISE;
  if (colorName[0] == '#' && strlen(colorName) >= 7) {
      unsigned long hexVal = strtoul(colorName + 1, NULL, 16);
      return strip.Color((hexVal >> 16) & 0xFF, (hexVal >> 8) & 0xFF, hexVal & 0xFF);
  }
  // RGB formatını dene: R,G,B
  int r, g, b;
  if (sscanf(colorName, "%d,%d,%d", &r, &g, &b) == 3) {
      return strip.Color(constrain(r,0,255), constrain(g,0,255), constrain(b,0,255));
  }
  return 0;
}

// Renkten RGB Alma
void getRGBFromColor(uint32_t color, uint8_t &r, uint8_t &g, uint8_t &b) {
  r = (color >> 16) & 0xFF;
  g = (color >> 8) & 0xFF;
  b = color & 0xFF;
}

// Komut Kuyruğu Fonksiyonları
void addToCommandQueue(String cmd) {
    cmd.trim();
    if(cmd.length() == 0) return;
    commandQueue[commandQueueTail] = cmd;
    commandQueueTail = (commandQueueTail + 1) % MAX_COMMANDS;
    if (commandQueueTail == commandQueueHead) {
        commandQueueHead = (commandQueueHead + 1) % MAX_COMMANDS;
        Serial.println("WARNING: Command queue overflow, dropping oldest command");
    }
    lastCommandTime = millis();
    commandProcessed = false;
}

bool hasCommand() { return commandQueueHead != commandQueueTail; }

String getNextCommand() {
    if (commandQueueHead == commandQueueTail) return "";
    String cmd = commandQueue[commandQueueHead];
    commandQueueHead = (commandQueueHead + 1) % MAX_COMMANDS;
    commandProcessed = true;
    return cmd;
}

// Renk tekerleği fonksiyonu (Mutex GEREKTİRMEZ)
uint32_t wheel(byte pos, uint32_t color = 0) {
    if (color != 0) {
      uint8_t r, g, b;
      getRGBFromColor(color, r, g, b);
      uint8_t maxChannel = max(r, max(g, b));
      float ratio = pos / 255.0;
      if (maxChannel == r && r > 0) {
           return strip.Color(r, (uint8_t)(g * ratio), (uint8_t)(b * ratio / 2));
      } else if (maxChannel == g && g > 0) {
          return strip.Color((uint8_t)(r * ratio / 2), g, (uint8_t)(b * ratio));
      } else if (b > 0){
          return strip.Color((uint8_t)(r * ratio), (uint8_t)(g * ratio / 2), b);
      } else {
          return strip.Color(0,0,0);
      }
    }
    pos = 255 - pos;
    if (pos < 85) {
      return strip.Color(255 - pos * 3, 0, pos * 3);
    } else if (pos < 170) {
      pos -= 85;
      return strip.Color(0, pos * 3, 255 - pos * 3);
    } else {
      pos -= 170;
      return strip.Color(pos * 3, 255 - pos * 3, 0);
    }
}

// --- Animasyon Fonksiyonları ---

void rainbow(uint32_t color = 0, int iterations = 1) {
  TickType_t mutexTimeout = pdMS_TO_TICKS(100);
  for (int j = 0; j < 256 * iterations; j++) {
    if (shouldAbortAnimation()) return;
    if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
      for (int i = g_segStart; i < g_segEnd; i++) {
        strip.setPixelColor(i, wheel((i + j) & 255, color));
      }
      strip.show();
      xSemaphoreGive(stripMutex);
    }
    if (delayOrAbort(20)) return;
  }
}

void rainbowCycle(uint32_t color = 0, int iterations = 1) {
  TickType_t mutexTimeout = pdMS_TO_TICKS(100);
  int segLen = max(1, g_segEnd - g_segStart);
  for (int j = 0; j < 256 * iterations; j++) {
    if (shouldAbortAnimation()) return;
    if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
      for (int i = g_segStart; i < g_segEnd; i++) {
        int pos = (((i - g_segStart) * 256 / segLen) + j) & 255;
        strip.setPixelColor(i, wheel(pos, color));
      }
      strip.show();
      xSemaphoreGive(stripMutex);
    }
    if (delayOrAbort(20)) return;
  }
}

void spinner(uint32_t color = COLOR_RED, int iterations = 1) {
  TickType_t mutexTimeout = pdMS_TO_TICKS(100);
   if (color == 0) color = COLOR_RED; 
  for (int iter = 0; iter < iterations; iter++) {
    for (int i = g_segStart; i < g_segEnd; i++) {
      if (shouldAbortAnimation()) return;
      if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
        strip.clear();
        strip.setPixelColor(i, color);
        strip.show();
        xSemaphoreGive(stripMutex);
      }
      if (delayOrAbort(100)) return;
    }
  }
}

void breathe(uint32_t color = COLOR_RED, int iterations = 1) {
  TickType_t mutexTimeout = pdMS_TO_TICKS(50);
   if (color == 0) color = COLOR_RED; 
  uint8_t r, g, b;
  getRGBFromColor(color, r, g, b);

  for (int iter = 0; iter < iterations; iter++) {
    for (int brightness = 0; brightness <= 255; brightness += 5) {
      if (shouldAbortAnimation()) return;
      if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
        uint32_t current_color = strip.Color((r * brightness) / 255, (g * brightness) / 255, (b * brightness) / 255);
        for (int i = g_segStart; i < g_segEnd; i++) strip.setPixelColor(i, current_color);
        strip.show();
        xSemaphoreGive(stripMutex);
      }
      if (delayOrAbort(20)) return;
    }
    for (int brightness = 255; brightness >= 0; brightness -= 5) {
       if (brightness < 0) brightness = 0;
       if (shouldAbortAnimation()) return;
      if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
         uint32_t current_color = strip.Color((r * brightness) / 255, (g * brightness) / 255, (b * brightness) / 255);
        for (int i = g_segStart; i < g_segEnd; i++) strip.setPixelColor(i, current_color);
        strip.show();
        xSemaphoreGive(stripMutex);
      }
      if (delayOrAbort(20)) return;
    }
     if (delayOrAbort(50)) return;
  }
}

void meteorRain(uint32_t color = COLOR_WHITE, int size = 5, int decay = 50, int repeat = 1) {
  TickType_t mutexTimeout = pdMS_TO_TICKS(50);
   if (color == 0) color = COLOR_WHITE;
  uint8_t r, g, b;
  getRGBFromColor(color, r, g, b);
  if (size < 1) size = 1;
  if (size > strip.numPixels()/2) size = strip.numPixels()/2;

  for (int iter = 0; iter < repeat; iter++) {
    for (int i = 0; i < strip.numPixels() + size; i++) {
      if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
        strip.clear();
        for (int j = 0; j < size; j++) {
          if ((i - j < strip.numPixels()) && (i - j >= 0)) {
            int brightness = 255 * (size - j) / size;
            strip.setPixelColor(i - j, strip.Color(
                (r * brightness / 255),
                (g * brightness / 255),
                (b * brightness / 255) ));
          }
        }
        strip.show();
        xSemaphoreGive(stripMutex);
      }
      vTaskDelay(pdMS_TO_TICKS(decay));
    }
  }
}

void fireFlicker(uint32_t color = COLOR_ORANGE, int repeat = 1) {
  TickType_t mutexTimeout = pdMS_TO_TICKS(50);
   if (color == 0) color = COLOR_ORANGE; 
  uint8_t r_base, g_base, b_base;
  getRGBFromColor(color, r_base, g_base, b_base);

  for (int iter = 0; iter < repeat * 10; iter++) {
    if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
      for (int i = 0; i < strip.numPixels(); i++) {
        int flicker = random(100, 256);
        int r_adj = constrain(r_base + random(-30, 20), 0, 255);
        int g_adj = constrain(g_base + random(-40, 10), 0, 255);
        int b_adj = constrain(b_base + random(-15, 5), 0, 255);
        float ratio = (float)flicker / 255.0;
        strip.setPixelColor(i, strip.Color(
            (uint8_t)(r_adj * ratio), (uint8_t)(g_adj * ratio), (uint8_t)(b_adj * ratio)));
      }
      strip.show();
      xSemaphoreGive(stripMutex);
    }
    vTaskDelay(pdMS_TO_TICKS(random(30, 120)));
  }
}

void comet(uint32_t color = strip.Color(0, 255, 255), int speed = 50, int repeat = 1) {
  TickType_t mutexTimeout = pdMS_TO_TICKS(50);
   if (color == 0) color = COLOR_CYAN; 
  uint8_t r, g, b;
  getRGBFromColor(color, r, g, b);
  int tailLength = 5;

  for (int iter = 0; iter < repeat; iter++) {
    for (int i = -tailLength; i < strip.numPixels(); i++) {
      if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
        strip.clear();
        for(int j = 0; j < tailLength; j++){
            if(i - j >= 0 && i - j < strip.numPixels()){
                int brightness = 255 * (tailLength - j) / tailLength;
                strip.setPixelColor(i-j, strip.Color(
                    (r * brightness / 255), (g * brightness / 255), (b * brightness / 255) ));
            }
        }
        strip.show();
        xSemaphoreGive(stripMutex);
      }
      vTaskDelay(pdMS_TO_TICKS(speed));
    }
  }
}

void wave(uint32_t color = 0, int repeat = 1) {
  TickType_t mutexTimeout = pdMS_TO_TICKS(50);
  for (int iter = 0; iter < repeat; iter++) {
    for (int j = 0; j < 256; j += 5) {
      if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
        for (int i = 0; i < strip.numPixels(); i++) {
          strip.setPixelColor(i, wheel(((i * 256 / strip.numPixels()) + j) & 255, color));
        }
        strip.show();
        xSemaphoreGive(stripMutex);
      }
      vTaskDelay(pdMS_TO_TICKS(50));
    }
  }
}

void pulse(uint32_t color = strip.Color(255, 0, 127), int repeat = 1) {
  TickType_t mutexTimeout = pdMS_TO_TICKS(50);
   if (color == 0) color = COLOR_MAGENTA; 
  uint8_t r, g, b;
  getRGBFromColor(color, r, g, b);

  for (int iter = 0; iter < repeat; iter++) {
    for (int brightness = 0; brightness < 255; brightness += 10) {
      if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
        float ratio = (float)brightness / 255.0;
        strip.fill(strip.Color((uint8_t)(r * ratio), (uint8_t)(g * ratio), (uint8_t)(b * ratio)));
        strip.show();
        xSemaphoreGive(stripMutex);
      }
      vTaskDelay(pdMS_TO_TICKS(50));
    }
    vTaskDelay(pdMS_TO_TICKS(100));
    for (int brightness = 255; brightness >= 0; brightness -= 10) {
      if(brightness < 0) brightness = 0;
      if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
        float ratio = (float)brightness / 255.0;
        strip.fill(strip.Color((uint8_t)(r * ratio), (uint8_t)(g * ratio), (uint8_t)(b * ratio)));
        strip.show();
        xSemaphoreGive(stripMutex);
      }
      vTaskDelay(pdMS_TO_TICKS(30));
    }
     vTaskDelay(pdMS_TO_TICKS(100));
  }
}

void twinkle(uint32_t color = COLOR_WHITE, int repeat = 1) {
  TickType_t mutexTimeout = pdMS_TO_TICKS(50);
   if (color == 0) color = COLOR_WHITE; 
  int numTwinkles = 10;
  int fadeAmount = 20; 

  for (int iter = 0; iter < repeat * 5; iter++) {
    if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
       for(int i=0; i<strip.numPixels(); i++) {
          uint32_t currentColor = strip.getPixelColor(i);
          if(currentColor != 0) {
             uint8_t r = (currentColor >> 16) & 0xFF;
             uint8_t g = (currentColor >> 8) & 0xFF;
             uint8_t b = currentColor & 0xFF;
             r = (r <= fadeAmount) ? 0 : r - fadeAmount;
             g = (g <= fadeAmount) ? 0 : g - fadeAmount;
             b = (b <= fadeAmount) ? 0 : b - fadeAmount;
             strip.setPixelColor(i, strip.Color(r,g,b));
          }
       }
      for (int i = 0; i < numTwinkles / 2; i++) {
        int index = random(strip.numPixels());
        strip.setPixelColor(index, color);
      }
      strip.show();
      xSemaphoreGive(stripMutex);
    }
    vTaskDelay(pdMS_TO_TICKS(100));
  }
   if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) { strip.clear(); strip.show(); xSemaphoreGive(stripMutex); }
}

void colorWipe(uint32_t color = COLOR_RED, int speed = 50, int repeat = 1) {
  TickType_t mutexTimeout = pdMS_TO_TICKS(50);
   if (color == 0) color = COLOR_RED; 
  uint8_t r, g, b;
  getRGBFromColor(color, r, g, b);

  for (int iter = 0; iter < repeat; iter++) {
    for (int i = 0; i < strip.numPixels(); i++) {
      if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
        strip.setPixelColor(i, strip.Color(r, g, b));
        strip.show();
        xSemaphoreGive(stripMutex);
      }
      vTaskDelay(pdMS_TO_TICKS(speed));
    }
    vTaskDelay(pdMS_TO_TICKS(speed * 2));
    for (int i = 0; i < strip.numPixels(); i++) {
      if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
        strip.setPixelColor(i, 0);
        strip.show();
        xSemaphoreGive(stripMutex);
      }
      vTaskDelay(pdMS_TO_TICKS(speed));
    }
     vTaskDelay(pdMS_TO_TICKS(speed * 2));
  }
}

void randomBlink(uint32_t color = 0, int repeat = 1) {
  TickType_t mutexTimeout = pdMS_TO_TICKS(50);
  for (int iter = 0; iter < repeat * 5; iter++) {
    if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
      if (color == 0) {
        for (int i = 0; i < strip.numPixels(); i++) {
          strip.setPixelColor(i, (random(5) == 0) ? strip.Color(random(255), random(255), random(255)) : 0);
        }
      } else { 
        uint8_t r, g, b;
        getRGBFromColor(color, r, g, b);
        for (int i = 0; i < strip.numPixels(); i++) {
          if(random(4) == 0) {
             int variation = random(-50, 50);
             int brightness_variation = random(150, 256);
             float ratio = (float)brightness_variation / 255.0;
            strip.setPixelColor(i, strip.Color(
                              (uint8_t)(constrain(r + variation, 0, 255) * ratio),
                              (uint8_t)(constrain(g + variation, 0, 255) * ratio),
                              (uint8_t)(constrain(b + variation, 0, 255) * ratio) ));
          } else {
              strip.setPixelColor(i, 0);
          }
        }
      }
      strip.show();
      xSemaphoreGive(stripMutex);
    }
    vTaskDelay(pdMS_TO_TICKS(100));
  }
   if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) { strip.clear(); strip.show(); xSemaphoreGive(stripMutex); }
}

void theaterChase(uint32_t color = strip.Color(127, 127, 127), int wait = 50, int repeat = 1) {
  TickType_t mutexTimeout = pdMS_TO_TICKS(50);
   if (color == 0) color = COLOR_WHITE; 
  for (int iter = 0; iter < repeat; iter++) {
    for (int q = 0; q < 3; q++) {
      if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
        strip.clear();
        for (int i = 0; i < strip.numPixels(); i += 3) {
          if(i + q < strip.numPixels()) {
             strip.setPixelColor(i + q, color);
          }
        }
        strip.show();
        xSemaphoreGive(stripMutex);
      }
      vTaskDelay(pdMS_TO_TICKS(wait));
    }
  }
   if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) { strip.clear(); strip.show(); xSemaphoreGive(stripMutex); }
}

void snow(uint32_t color = COLOR_WHITE, int repeat = 1) {
  TickType_t mutexTimeout = pdMS_TO_TICKS(50);
   if (color == 0) color = COLOR_WHITE; 
  int numFlakes = 10;

  for (int iter = 0; iter < repeat * 5; iter++) {
    if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
      strip.clear();
      uint8_t r, g, b;
      getRGBFromColor(color, r, g, b);
      for (int i = 0; i < numFlakes; i++) {
        int snowflakePos = random(strip.numPixels());
        int intensity = random(100, 255);
        float ratio = intensity / 255.0;
        strip.setPixelColor(snowflakePos, strip.Color(
            (uint8_t)(r * ratio), (uint8_t)(g * ratio), (uint8_t)(b * ratio)));
      }
      strip.show();
      xSemaphoreGive(stripMutex);
    }
    vTaskDelay(pdMS_TO_TICKS(200));
  }
    if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) { strip.clear(); strip.show(); xSemaphoreGive(stripMutex); }
}

void alternatingColors(uint32_t color1 = COLOR_RED, uint32_t color2 = COLOR_BLUE, int cycles = 10, int wait = 100) {
  TickType_t mutexTimeout = pdMS_TO_TICKS(50);
   if (color1 == 0) color1 = COLOR_RED; 
   if (color2 == 0) color2 = COLOR_BLUE;
  for (int j = 0; j < cycles; j++) {
    if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
      for (int i = 0; i < strip.numPixels(); i++) {
        strip.setPixelColor(i, ( (i + j) % 2 == 0) ? color1 : color2);
      }
      strip.show();
      xSemaphoreGive(stripMutex);
    }
    vTaskDelay(pdMS_TO_TICKS(wait));
  }
}

void multiColorGradient(uint32_t colors[], int colorCount, int iterations = 1) {
  if (colorCount < 2) return; 
  TickType_t mutexTimeout = pdMS_TO_TICKS(50);

  for (int iter = 0; iter < iterations; iter++) {
    if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
        for (int i = 0; i < strip.numPixels(); i++) {
            float overallPos = (float)i / (strip.numPixels() - 1);
            int segment = (int)(overallPos * (colorCount - 1));
            float segmentPos = (overallPos * (colorCount - 1)) - segment;
             segment = constrain(segment, 0, colorCount - 2);

            uint32_t color1 = colors[segment];
            uint32_t color2 = colors[segment + 1];
            if(color1 == 0 && segment > 0) color1 = colors[segment-1];
            if(color2 == 0 && segment < colorCount - 2) color2 = colors[segment+2];
            if(color1 == 0) color1 = COLOR_BLACK; 
            if(color2 == 0) color2 = COLOR_BLACK; 

            uint8_t r1, g1, b1, r2, g2, b2;
            getRGBFromColor(color1, r1, g1, b1);
            getRGBFromColor(color2, r2, g2, b2);

            uint8_t r = (uint8_t)(r1 + (r2 - r1) * segmentPos);
            uint8_t g = (uint8_t)(g1 + (g2 - g1) * segmentPos);
            uint8_t b = (uint8_t)(b1 + (b2 - b1) * segmentPos);

            strip.setPixelColor(i, strip.Color(r, g, b));
        }
        strip.show();
        xSemaphoreGive(stripMutex);
    }
     vTaskDelay(pdMS_TO_TICKS(iterations > 1 ? 500 : 0)); 
  }
}

void multiColorWave(uint32_t colors[], int colorCount, int iterations = 5) {
  if (colorCount < 1) return; 
  TickType_t mutexTimeout = pdMS_TO_TICKS(50);

  for (int iter = 0; iter < iterations; iter++) {
    for (int j = 0; j < 256; j += 5) {
      if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
        for (int i = 0; i < strip.numPixels(); i++) {
          int cyclePos = (i * 256 / strip.numPixels() + j) & 255;
          int segment = (cyclePos * colorCount) / 256;
          int segmentPos = (cyclePos * colorCount) % 256;

          uint32_t color1 = colors[segment % colorCount];
          uint32_t color2 = colors[(segment + 1) % colorCount];
          if(color1 == 0) color1 = colors[(segment + colorCount -1) % colorCount];
          if(color2 == 0) color2 = colors[(segment + 2) % colorCount];
          if(color1 == 0) color1 = COLOR_BLACK; 
          if(color2 == 0) color2 = COLOR_BLACK; 

          uint8_t r1, g1, b1, r2, g2, b2;
          getRGBFromColor(color1, r1, g1, b1);
          getRGBFromColor(color2, r2, g2, b2);

          float ratio = (float)segmentPos / 255.0;
          uint8_t r = (uint8_t)(r1 + (r2 - r1) * ratio);
          uint8_t g = (uint8_t)(g1 + (g2 - g1) * ratio);
          uint8_t b = (uint8_t)(b1 + (b2 - b1) * ratio);

          strip.setPixelColor(i, strip.Color(r, g, b));
        }
        strip.show();
        xSemaphoreGive(stripMutex);
      }
      vTaskDelay(pdMS_TO_TICKS(30));
    }
  }
}

void gradientFade(int cycles = 5, uint32_t color = 0) {
   TickType_t mutexTimeout = pdMS_TO_TICKS(50);
  for (int j = 0; j < 256 * cycles; j+=4) {
      if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
          for (int i = 0; i < strip.numPixels(); i++) {
                int pos = map(i, 0, strip.numPixels() - 1, 0, 255);
                strip.setPixelColor(i, wheel((pos + j) & 255, color));
          }
          strip.show();
          xSemaphoreGive(stripMutex);
      }
      vTaskDelay(pdMS_TO_TICKS(30));
  }
}

void bouncingBall(uint32_t color = COLOR_RED, int repeat = 1) {
  TickType_t mutexTimeout = pdMS_TO_TICKS(50);
   if (color == 0) color = COLOR_RED; 
  uint8_t r, g, b;
  getRGBFromColor(color, r, g, b);
  int numBalls = 3;
  float h[numBalls];
  float v[numBalls];
  float gravity = -0.08;
  float dampening = 0.85;

  for (int i = 0; i < numBalls; i++) {
      h[i] = random(strip.numPixels());
      v[i] = ((float)random(10, 120))/100.0;
  }

  for (int iter = 0; iter < repeat * 100; iter++) {
      if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
          strip.clear();
           for(int i=0; i<numBalls; i++) {
                h[i] += v[i];
                v[i] += gravity;
                if (h[i] <= 0) {
                    h[i] = 0;
                    v[i] = -v[i] * dampening;
                    if (abs(v[i]) < 0.1) { v[i] = ((float)random(50, 120))/100.0; h[i] = 0.1; }
                }
                if(h[i] >= strip.numPixels() - 1) {
                    h[i] = strip.numPixels() - 1;
                    v[i] = -v[i] * dampening;
                }
                int pos = (int)h[i];
                pos = constrain(pos, 0, strip.numPixels() - 1);
                strip.setPixelColor(pos, strip.Color(r, g, b));
                if(pos > 0) strip.setPixelColor(pos - 1, strip.Color(r/4, g/4, b/4));
           }
          strip.show();
          xSemaphoreGive(stripMutex);
      }
      vTaskDelay(pdMS_TO_TICKS(30));
  }
   if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) { strip.clear(); strip.show(); xSemaphoreGive(stripMutex); }
}

void runningLights(uint32_t color = COLOR_RED, int wait = 50, int repeat = 1) {
  TickType_t mutexTimeout = pdMS_TO_TICKS(50);
   if (color == 0) color = COLOR_RED; 
  uint8_t r, g, b;
  getRGBFromColor(color, r, g, b);
  int waveLength = 10;

  for (int iter = 0; iter < repeat; iter++) {
    for (int j = 0; j < strip.numPixels() * 2; j++) {
      if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
        for (int i = 0; i < strip.numPixels(); i++) {
          float level = sin( (float)(i + j) * PI * 2.0 / waveLength );
          level = (level + 1.0) / 2.0;
          strip.setPixelColor(i, strip.Color(
                            (uint8_t)(r * level), (uint8_t)(g * level), (uint8_t)(b * level) ));
        }
        strip.show();
        xSemaphoreGive(stripMutex);
      }
      vTaskDelay(pdMS_TO_TICKS(wait));
    }
  }
}

void stackedBars(int wait = 50, uint32_t color = 0, int repeat = 1) {
  TickType_t mutexTimeout = pdMS_TO_TICKS(50);
  for (int iter = 0; iter < repeat; iter++) {
    for (int h = 0; h < strip.numPixels(); h++) {
      if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
        uint32_t barColor = (color == 0) ? wheel(map(h, 0, strip.numPixels() - 1, 0, 255)) : color;
        strip.setPixelColor(h, barColor);
        strip.show();
        xSemaphoreGive(stripMutex);
      }
      vTaskDelay(pdMS_TO_TICKS(wait));
    }
    for (int h = strip.numPixels() - 1; h >= 0; h--) {
      if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
        strip.setPixelColor(h, 0);
        strip.show();
        xSemaphoreGive(stripMutex);
      }
      vTaskDelay(pdMS_TO_TICKS(wait));
    }
  }
}

void eyeEyebrow(uint32_t color = COLOR_TURQUOISE, int iterations = 1) {
  TickType_t mutexTimeout = pdMS_TO_TICKS(50);
  if (color == 0) color = COLOR_TURQUOISE;
  uint8_t r, g, b;
  getRGBFromColor(color, r, g, b);
  uint8_t oppR = 255 - r, oppG = 255 - g, oppB = 255 - b;
  for (int iter = 0; iter < iterations; iter++) {
    for (int step = 0; step < 20; step++) {
      if (shouldAbortAnimation()) return;
      float phase = (float)step / 20.0;
      float pulseVal = 0.45 + 0.55 * (0.5 + 0.5 * sin(phase * 2.0 * PI));
      float browVal = 0.2 + 0.5 * (0.5 + 0.5 * cos(phase * PI));
      if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
        for (int i = g_segStart; i < g_segEnd; i++) {
          if (i < 7) {
            if (i == 0) strip.setPixelColor(i, strip.Color((uint8_t)(oppR * pulseVal), (uint8_t)(oppG * pulseVal), (uint8_t)(oppB * pulseVal)));
            else strip.setPixelColor(i, strip.Color((uint8_t)(r * 0.15), (uint8_t)(g * 0.15), (uint8_t)(b * 0.15)));
          } else {
            strip.setPixelColor(i, strip.Color((uint8_t)(r * browVal), (uint8_t)(g * browVal), (uint8_t)(b * browVal)));
          }
        }
        strip.show();
        xSemaphoreGive(stripMutex);
      }
      if (delayOrAbort(50)) return;
    }
  }
}

void emotionalPulse(uint32_t color = COLOR_CYAN, int iterations = 1) {
  TickType_t mutexTimeout = pdMS_TO_TICKS(50);
  if (color == 0) color = COLOR_CYAN;
  uint8_t r, g, b;
  getRGBFromColor(color, r, g, b);
  for (int iter = 0; iter < iterations; iter++) {
    for (int step = 0; step < 20; step++) {
      if (shouldAbortAnimation()) return;
      float phase = (float)step / 20.0;
      float beat = sin(phase * 2.0 * PI);
      float intensity = 0.15 + 0.85 * max(0.0f, beat);
      if (xSemaphoreTake(stripMutex, mutexTimeout) == pdTRUE) {
        for (int i = g_segStart; i < g_segEnd; i++) {
          strip.setPixelColor(i, strip.Color((uint8_t)(r * intensity), (uint8_t)(g * intensity), (uint8_t)(b * intensity)));
        }
        strip.show();
        xSemaphoreGive(stripMutex);
      }
      if (delayOrAbort(50)) return;
    }
  }
}

// --- Animasyon Görevi ---
void animationTask(void *pvParameters) {
  AnimationCommand cmd;
  Serial.println("Animation Task started on Core 1");
  uint32_t multiColors[10]; 
  int multiColorCount = 0;

  for (;;) {
    if (xQueueReceive(animationCommandQueue, &cmd, portMAX_DELAY) == pdPASS) {
        g_abortAnimation = false;
        g_preserveStaticPixels = false;
        segmentRange(cmd.segment, g_segStart, g_segEnd);
        multiColorCount = 0;
        if(cmd.color1 != 0) multiColors[multiColorCount++] = cmd.color1;
        if(cmd.color2 != 0) multiColors[multiColorCount++] = cmd.color2;

      if (strcmp(cmd.name, "RAINBOW") == 0) rainbow(cmd.color1, cmd.repeat);
      else if (strcmp(cmd.name, "RAINBOW_CYCLE") == 0) rainbowCycle(cmd.color1, cmd.repeat);
      else if (strcmp(cmd.name, "SPINNER") == 0) spinner(cmd.color1, cmd.repeat);
      else if (strcmp(cmd.name, "BREATHE") == 0) breathe(cmd.color1, cmd.repeat);
      else if (strcmp(cmd.name, "METEOR") == 0) meteorRain(cmd.color1, 5, 50, cmd.repeat);
      else if (strcmp(cmd.name, "FIRE") == 0) fireFlicker(cmd.color1, cmd.repeat);
      else if (strcmp(cmd.name, "COMET") == 0) comet(cmd.color1, 50, cmd.repeat);
      else if (strcmp(cmd.name, "WAVE") == 0) wave(cmd.color1, cmd.repeat);
      else if (strcmp(cmd.name, "PULSE") == 0) pulse(cmd.color1, cmd.repeat);
      else if (strcmp(cmd.name, "TWINKLE") == 0) twinkle(cmd.color1, cmd.repeat);
      else if (strcmp(cmd.name, "COLOR_WIPE") == 0 || strcmp(cmd.name, "WIPE") == 0) colorWipe(cmd.color1, 50, cmd.repeat);
      else if (strcmp(cmd.name, "RANDOM_BLINK") == 0 || strcmp(cmd.name, "BLINK") == 0) randomBlink(cmd.color1, cmd.repeat);
      else if (strcmp(cmd.name, "THEATER_CHASE") == 0 || strcmp(cmd.name, "CHASE") == 0) theaterChase(cmd.color1, 50, cmd.repeat);
      else if (strcmp(cmd.name, "SNOW") == 0) snow(cmd.color1, cmd.repeat);
      else if (strcmp(cmd.name, "ALTERNATING") == 0 || strcmp(cmd.name, "ALT") == 0) alternatingColors(cmd.color1, cmd.color2, cmd.repeat * 5, 100);
      else if (strcmp(cmd.name, "GRADIENT") == 0) gradientFade(cmd.repeat, cmd.color1);
      else if (strcmp(cmd.name, "BOUNCING_BALL") == 0 || strcmp(cmd.name, "BOUNCE") == 0) bouncingBall(cmd.color1, cmd.repeat);
      else if (strcmp(cmd.name, "RUNNING_LIGHTS") == 0 || strcmp(cmd.name, "RUN") == 0) runningLights(cmd.color1, 50, cmd.repeat);
      else if (strcmp(cmd.name, "STACKED_BARS") == 0 || strcmp(cmd.name, "STACK") == 0) stackedBars(50, cmd.color1, cmd.repeat);
      else if (strcmp(cmd.name, "EYE_EYEBROW") == 0) eyeEyebrow(cmd.color1, cmd.repeat);
      else if (strcmp(cmd.name, "EMOTIONAL_PULSE") == 0) emotionalPulse(cmd.color1, cmd.repeat);
      else if (strcmp(cmd.name, "MULTI_GRADIENT") == 0 || strcmp(cmd.name, "M_GRAD") == 0) {
           if(multiColorCount >= 2) multiColorGradient(multiColors, multiColorCount, cmd.repeat);
      }
      else if (strcmp(cmd.name, "MULTI_WAVE") == 0 || strcmp(cmd.name, "M_WAVE") == 0) {
           if(multiColorCount >= 1) multiColorWave(multiColors, multiColorCount, cmd.repeat);
      }

      if (!g_preserveStaticPixels && !shouldAbortAnimation()) {
        if (xSemaphoreTake(stripMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
          strip.clear();
          strip.show();
          xSemaphoreGive(stripMutex);
        }
      }
    }
  }
}

// --- Seri Giriş İşleme ---
void processSerialInput() {
  static String currentCommand = "";
  static unsigned long lastCommandAdded = 0;

  if (millis() - lastCommandAdded < 10) { return; }

  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c < 0x20 && c != '\n' && c != '\r') {
      serialErrorCount++;
      if (serialErrorCount > MAX_SERIAL_ERRORS) {
        currentCommand = "";
        serialErrorCount = 0;
        while (Serial.available()) { Serial.read(); }
        break;
      }
      continue;
    }

    if (c == '\n' || c == '\r') {
      if (currentCommand.length() > 0) {
        addToCommandQueue(currentCommand);
        lastCommandAdded = millis();
        currentCommand = "";
        serialErrorCount = 0;
      }
    } else {
      if (currentCommand.length() < MAX_COMMAND_LENGTH - 1) {
        currentCommand += c;
      } else {
        currentCommand = "";
        while (Serial.available() && Serial.read() != '\n') {}
      }
    }
  }
}

// --- SETUP ---
void setup() {
  Serial.begin(115200);
  delay(1500); 
  Serial.println("\n\n--- Initializing ESP32 NeoPixel Controller ---");

  while (Serial.available()) { Serial.read(); }

  stripMutex = xSemaphoreCreateMutex();
  animationCommandQueue = xQueueCreate(5, sizeof(AnimationCommand)); 

  if (stripMutex == NULL || animationCommandQueue == NULL) {
    Serial.println("FATAL ERROR: Failed to create RTOS objects!");
    ESP.restart();
  }

  // NeoPixel Başlatma
  if (xSemaphoreTake(stripMutex, pdMS_TO_TICKS(200)) == pdTRUE) { 
    strip.begin();
    strip.setBrightness(255); 
    strip.show(); 
    xSemaphoreGive(stripMutex);
  }

  // Görevleri Oluştur ve Başlat
  xTaskCreatePinnedToCore( animationTask, "AnimTask", 4096, NULL, 2, &animationTaskHandle, 1);

  delay(500);

  Serial.println("\nESP32 NeoPixel controller ready");
  Serial.println("Available commands:");
  Serial.println("  SET [idx] [r] [g] [b]");
  Serial.println("  ANIMATE [NAME] [C1] [C2] [REP] (Colors: NAME or R,G,B; C2/REP optional)");

  // Başlangıç Animasyonu
  AnimationCommand startupCmd;
  memset(&startupCmd, 0, sizeof(startupCmd)); 
  strcpy(startupCmd.name, "WAVE");           
  startupCmd.color1 = 0;                     
  startupCmd.color2 = 0;
  startupCmd.repeat = 1;                     

  xQueueSend(animationCommandQueue, &startupCmd, pdMS_TO_TICKS(100));
}

// --- LOOP ---
void loop() {
  if (millis() - lastSerialCheck > SERIAL_THROTTLE_TIME) {
    lastSerialCheck = millis();
    processSerialInput(); 
  }

  if (hasCommand()) {
    String cmd = getNextCommand();
    String cmdUpper = cmd;
    cmdUpper.toUpperCase();

    if (cmdUpper == "CLEAR") {
      g_abortAnimation = true;
      g_preserveStaticPixels = true;
      if (xSemaphoreTake(stripMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
        strip.clear();
        strip.show();
        xSemaphoreGive(stripMutex);
      }
    }
    else if (cmdUpper.startsWith("SET ")) {
      int idx, r, g, b;
      if (sscanf(cmdUpper.c_str(), "SET %d %d %d %d", &idx, &r, &g, &b) == 4 && idx >= 0 && idx < LED_COUNT) {
        r = constrain(r, 0, 255);
        g = constrain(g, 0, 255);
        b = constrain(b, 0, 255);
        g_abortAnimation = true;
        g_preserveStaticPixels = true;
        if (xSemaphoreTake(stripMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
          strip.setPixelColor(idx, strip.Color(r, g, b));
          strip.show();
          xSemaphoreGive(stripMutex);
          Serial.printf("Set LED %d to R:%d G:%d B:%d\n", idx, r, g, b);
        }
      }
    }
    else if (cmdUpper.startsWith("ANIMATE")) {
        AnimationCommand animCmd;
        memset(&animCmd, 0, sizeof(animCmd));
        animCmd.repeat = 1;

        char animName[24] = "";
        char segName[16] = "";
        char color1Str[20] = "";
        char color2Str[20] = "";
        char repeatStr[8] = "";

        char cmdBuffer[MAX_COMMAND_LENGTH];
        cmdUpper.toCharArray(cmdBuffer, sizeof(cmdBuffer));
        char* token = strtok(cmdBuffer, " ");
        int part = 0;

        while (token != NULL) {
            if (part > 0) {
                if (part == 1) {
                    strncpy(animName, token, sizeof(animName) - 1);
                } else if (strncmp(token, "SEG=", 4) == 0) {
                    strncpy(segName, token + 4, sizeof(segName) - 1);
                } else {
                    bool isNumber = true;
                    for (size_t k = 0; k < strlen(token); k++) {
                        if (!isdigit((unsigned char)token[k])) { isNumber = false; break; }
                    }
                    if (isNumber) {
                        strncpy(repeatStr, token, sizeof(repeatStr) - 1);
                    } else {
                        if (strlen(color1Str) == 0) strncpy(color1Str, token, sizeof(color1Str) - 1);
                        else if (strlen(color2Str) == 0) strncpy(color2Str, token, sizeof(color2Str) - 1);
                    }
                }
            }
            token = strtok(NULL, " ");
            part++;
        }

        if (strlen(animName) > 0) {
            g_abortAnimation = true;
            g_preserveStaticPixels = false;
            strncpy(animCmd.name, animName, sizeof(animCmd.name) - 1);
            strncpy(animCmd.segment, segName, sizeof(animCmd.segment) - 1);
            animCmd.color1 = getColorFromString(color1Str);
            animCmd.color2 = getColorFromString(color2Str);
            if (strlen(repeatStr) > 0) animCmd.repeat = atoi(repeatStr);
            animCmd.repeat = constrain(animCmd.repeat, 1, 10);

            xQueueSend(animationCommandQueue, &animCmd, pdMS_TO_TICKS(50));
        }
    }
  } 

  if (!commandProcessed && (millis() - lastCommandTime > 5000)) {
    commandProcessed = true;
  }

  vTaskDelay(pdMS_TO_TICKS(10));
}