#ifndef ROBOT_PERIPHERALS_H
#define ROBOT_PERIPHERALS_H

#include <Arduino.h>
#include "xConfig.h"

#if BUZZER_ENABLED
#include <avr/pgmspace.h>
#endif

#if IR_ENABLED
// Requires Arduino Library: IRremote (v4+)
#include <IRremote.hpp>
#endif

#if RFID_ENABLED
#include <SPI.h>
#include <MFRC522.h>
#endif

#if LCD_ENABLED
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#endif

// Lightweight wrappers to keep xMain clean

class Ultrasonic {
public:
  void begin(uint8_t trigPin, uint8_t echoPin){
    _trig=trigPin; _echo=echoPin; pinMode(_trig, OUTPUT); pinMode(_echo, INPUT);
    _lastMs = 0; _lastCm = NAN;
  }
  // Measure with small timeouts to avoid blocking long
  bool measureIfDue(unsigned long intervalMs){
    unsigned long now = millis();
    if (now - _lastMs < intervalMs) return false;
    _lastMs = now;
    digitalWrite(_trig, LOW); delayMicroseconds(2);
    digitalWrite(_trig, HIGH); delayMicroseconds(10);
    digitalWrite(_trig, LOW);
    unsigned long dur = pulseIn(_echo, HIGH, 30000UL); // 30ms timeout ≈ ~5m
    if (dur==0){ _lastCm = NAN; }
    else { _lastCm = (float)dur / 58.0f; }
    return true;
  }
  float lastCm() const { return _lastCm; }
private:
  uint8_t _trig=255, _echo=255; unsigned long _lastMs=0; float _lastCm=NAN;
};

#if RFID_ENABLED
class RfidReader {
public:
  void begin(uint8_t ssPin, uint8_t rstPin){
    SPI.begin(); _mfrc = new MFRC522(ssPin, rstPin); _mfrc->PCD_Init();
    _lastUid = ""; _lastSeenMs=0;
  }
  // Returns true when a new UID is read
  bool poll(){
    if (!_mfrc) return false;
    if (!_mfrc->PICC_IsNewCardPresent() || !_mfrc->PICC_ReadCardSerial()) return false;
    String uid = uidToHex(_mfrc->uid);
    bool isNew = (uid != _lastUid);
    _lastUid = uid; _lastSeenMs = millis();
    _mfrc->PICC_HaltA(); _mfrc->PCD_StopCrypto1();
    if (isNew) { _lastEventUid = uid; return true; }
    return false;
  }
  const String &lastUid() const { return _lastUid; }
  // If a new UID was just read in poll(), returns it once; else empty
  String takeLastEvent(){ String t=_lastEventUid; _lastEventUid=""; return t; }
private:
  static String uidToHex(const MFRC522::Uid &u){
    String s; for (byte i=0;i<u.size;i++){ if (i) s+=""; if (u.uidByte[i]<16) s += "0"; s += String(u.uidByte[i], HEX); }
    s.toUpperCase(); return s;
  }
  MFRC522 *_mfrc{nullptr}; String _lastUid; String _lastEventUid; unsigned long _lastSeenMs{0};
};
#endif

#if LCD_ENABLED
class LcdDisplay {
public:
  void begin(){
    int hwRows = (LCD_ROWS==1?2:LCD_ROWS); // bazı 16x1 modüller 8x2 adresleme kullanır
    _lcd = new LiquidCrystal_I2C(LCD_I2C_ADDR, LCD_COLS, hwRows);
    _lcd->init(); _lcd->backlight(); clear();
  }
  void clear(){
    if (!_lcd) return;
    _lcd->clear();
    // 16x1 büyük font (8x2 adresleme) için iki yarıyı boşlukla temizle
    if (LCD_ROWS==1){
      _lcd->setCursor(0,0); _lcd->print("        ");
      if (LCD_16X1_SPLIT_ROW){
        _lcd->setCursor(0,1);
      } else {
        _lcd->setCursor(8,0);
      }
      _lcd->print("        ");
      _lcd->setCursor(0,0);
    } else {
      _lcd->setCursor(0,0);
    }
  }
  void printLine(const String &msg){
    if (!_lcd) return;
    String m = msg;
    if ((int)m.length()>LCD_COLS) m = m.substring(0, LCD_COLS);
    if (LCD_ROWS==1){
      // 16x1 büyük font: ilk 8 karakter satır 0'a, sonraki 8 satır 1'e yazılır
      String s0 = m.substring(0, min(8, (int)m.length()));
      while ((int)s0.length() < 8) s0 += ' ';
      String s1 = (m.length()>8)? m.substring(8) : String("");
      while ((int)s1.length() < 8) s1 += ' ';
      _lcd->setCursor(0,0); _lcd->print(s0);
      if (LCD_16X1_SPLIT_ROW){
        _lcd->setCursor(0,1);
      } else {
        _lcd->setCursor(8,0);
      }
      _lcd->print(s1);
      _lcd->setCursor(0,0);
    } else {
      // Klasik 16x2 vb.
      // Satırı temizle ve yaz
      _lcd->setCursor(0,0);
      for (int i=0;i<LCD_COLS;i++) _lcd->print(' ');
      _lcd->setCursor(0,0); _lcd->print(m);
    }
  }
private:
  LiquidCrystal_I2C *_lcd{nullptr};
};
#endif

#if LASER_ENABLED
class LaserPair {
public:
  void begin(uint8_t pin1, uint8_t pin2){
    _p1 = pin1; _p2 = pin2; pinMode(_p1, OUTPUT); pinMode(_p2, OUTPUT); off();
  }
  void oneOn(uint8_t idx){
    if (idx==1) digitalWrite(_p1, LASER_ACTIVE_HIGH?HIGH:LOW);
    else if (idx==2) digitalWrite(_p2, LASER_ACTIVE_HIGH?HIGH:LOW);
  }
  void bothOn(){
    digitalWrite(_p1, LASER_ACTIVE_HIGH?HIGH:LOW);
    digitalWrite(_p2, LASER_ACTIVE_HIGH?HIGH:LOW);
  }
  void off(){
    digitalWrite(_p1, LASER_ACTIVE_HIGH?LOW:HIGH);
    digitalWrite(_p2, LASER_ACTIVE_HIGH?LOW:HIGH);
  }
private:
  uint8_t _p1{255}, _p2{255};
};
#endif

#if BUZZER_ENABLED
enum BuzzerOut : uint8_t {
  BUZZER_OUT_LOUD = 0,
  BUZZER_OUT_QUIET = 1,
};

class BuzzerPair {
public:
  void begin(uint8_t loudPin, uint8_t quietPin){
    _loud = loudPin; _quiet = quietPin;
    pinMode(_loud, OUTPUT);
    pinMode(_quiet, OUTPUT);
    stop();
  }

  void beepOn(BuzzerOut out, uint16_t freqHz = 2200, uint16_t ms = 60){
    uint8_t pin = selectPin(out);
    if (pin == 255) return;

#if BUZZER_USE_TONE
    tone(pin, freqHz, ms);
#else
    digitalWrite(pin, HIGH);
    delay(ms);
    digitalWrite(pin, LOW);
#endif
  }

  void stop(){
#if BUZZER_USE_TONE
    if (_loud != 255) noTone(_loud);
    if (_quiet != 255) noTone(_quiet);
#endif
    if (_loud != 255) digitalWrite(_loud, LOW);
    if (_quiet != 255) digitalWrite(_quiet, LOW);
  }

private:
  uint8_t selectPin(BuzzerOut out) const {
    return (out == BUZZER_OUT_LOUD) ? _loud : _quiet;
  }

  uint8_t _loud{255}, _quiet{255};
};

struct BuzzerNote {
  uint16_t freq;
  uint16_t durMs;
  uint16_t gapMs;
};

class BuzzerSongPlayer {
public:
  void begin(BuzzerPair *pair){ _pair = pair; stop(); }

  void setDefaultOut(BuzzerOut out){ _defaultOut = out; }
  BuzzerOut defaultOut() const { return _defaultOut; }

  void play(const String &name, BuzzerOut out){
    const BuzzerNote *song = nullptr;
    uint8_t len = 0;
    if (!resolveSong(name, song, len)) return;
    _song = song;
    _len = len;
    _idx = 0;
    _out = out;
    _state = PLAYING;
    _nextMs = 0;
  }

  void playDefault(const String &name){ play(name, _defaultOut); }

  void stop(){
    _state = IDLE;
    _song = nullptr;
    _len = 0;
    _idx = 0;
    _nextMs = 0;
  }

  void update(){
    if (_state == IDLE || !_pair || !_song || _len == 0) return;
    unsigned long now = millis();
    if (_nextMs != 0 && now < _nextMs) return;

    if (_idx >= _len){
      stop();
      return;
    }

    BuzzerNote n;
    n.freq = pgm_read_word(&_song[_idx].freq);
    n.durMs = pgm_read_word(&_song[_idx].durMs);
    n.gapMs = pgm_read_word(&_song[_idx].gapMs);

    if (n.freq > 0 && n.durMs > 0){
      _pair->beepOn(_out, n.freq, n.durMs);
      _nextMs = now + (unsigned long)n.durMs + (unsigned long)n.gapMs;
    } else {
      _nextMs = now + (unsigned long)n.gapMs;
    }
    _idx++;
  }

private:
  enum State : uint8_t { IDLE=0, PLAYING=1 };

  static bool resolveSong(const String &name, const BuzzerNote *&outSong, uint8_t &outLen){
    if (name.equalsIgnoreCase("walle") || name.equalsIgnoreCase("wall-e")){
      outSong = SONG_WALLE; outLen = (uint8_t)(sizeof(SONG_WALLE)/sizeof(SONG_WALLE[0])); return true;
    }
    if (name.equalsIgnoreCase("bb8") || name.equalsIgnoreCase("bb-8")){
      outSong = SONG_BB8; outLen = (uint8_t)(sizeof(SONG_BB8)/sizeof(SONG_BB8[0])); return true;
    }
    return false;
  }

  // Minimal melodies: short and distinctive (passive buzzer).
  static const BuzzerNote SONG_WALLE[] PROGMEM;
  static const BuzzerNote SONG_BB8[] PROGMEM;

  BuzzerPair *_pair{nullptr};
  const BuzzerNote *_song{nullptr};
  uint8_t _len{0};
  uint8_t _idx{0};
  unsigned long _nextMs{0};
  BuzzerOut _defaultOut{BUZZER_OUT_QUIET};
  BuzzerOut _out{BUZZER_OUT_QUIET};
  State _state{IDLE};
};

// Definitions
const BuzzerNote BuzzerSongPlayer::SONG_WALLE[] PROGMEM = {
  {880, 80, 30}, {0, 0, 40}, {1319, 120, 50}, {988, 90, 80}, {1175, 140, 60},
  {0, 0, 70}, {784, 120, 40}, {988, 160, 100},
};

const BuzzerNote BuzzerSongPlayer::SONG_BB8[] PROGMEM = {
  {1760, 40, 20}, {1976, 40, 20}, {2093, 50, 30}, {0, 0, 40},
  {1568, 70, 30}, {2093, 60, 40}, {0, 0, 60}, {2349, 80, 120},
};
#endif

#if IR_ENABLED
class IrKeyReader {
public:
  void begin(uint8_t pin){
    IrReceiver.begin(pin, ENABLE_LED_FEEDBACK);
  }

  // Returns true when a key is decoded; outKey is one of: "0".."9","*","#","UP","DOWN","LEFT","RIGHT","OK","UNKNOWN"
  bool poll(String &outKey){
    if (!IrReceiver.decode()) return false;
    uint32_t code = IrReceiver.decodedIRData.decodedRawData;
    IrReceiver.resume();
    outKey = decodeToKey(code);
    return true;
  }

private:
  static String decodeToKey(uint32_t code){
    switch(code){
      case 0xBA45FF00: return "1";
      case 0xB946FF00: return "2";
      case 0xB847FF00: return "3";
      case 0xBB44FF00: return "4";
      case 0xBF40FF00: return "5";
      case 0xBC43FF00: return "6";
      case 0xF807FF00: return "7";
      case 0xEA15FF00: return "8";
      case 0xF609FF00: return "9";
      case 0xE916FF00: return "*";
      case 0xE619FF00: return "0";
      case 0xF20DFF00: return "#";
      case 0xE718FF00: return "UP";
      case 0xF708FF00: return "LEFT";
      case 0xE31CFF00: return "OK";
      case 0xA55AFF00: return "RIGHT";
      case 0xAD52FF00: return "DOWN";
      default: return "UNKNOWN";
    }
  }
};
#endif

#endif // ROBOT_PERIPHERALS_H