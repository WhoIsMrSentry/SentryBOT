#ifndef SENTRY_PERIPHERALS_LCD_DISPLAY_H
#define SENTRY_PERIPHERALS_LCD_DISPLAY_H

#include <Arduino.h>
#include "../xConfig.h"

#if LCD_ENABLED
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

class LcdDisplay {
public:
  void begin(){ begin(LCD_I2C_ADDR, LCD_COLS, LCD_ROWS, LCD_16X1_SPLIT_ROW); }

  void begin(uint8_t addr, uint8_t cols, uint8_t rows, bool splitRow16x1){
    _addr = addr;
    _cols = cols;
    _rows = rows;
    _splitRow16x1 = splitRow16x1;

    int hwRows = (_rows == 1 ? 2 : _rows); // bazı 16x1 modüller 8x2 adresleme kullanır
    _lcd = new LiquidCrystal_I2C(_addr, _cols, hwRows);
    _lcd->init();
    _lcd->backlight();
    
    // Define custom icons
    uint8_t iconArrow[8] = {0x00, 0x04, 0x06, 0x1F, 0x06, 0x04, 0x00, 0x00}; // ->
    uint8_t iconTemp[8]  = {0x04, 0x0A, 0x0A, 0x0E, 0x0E, 0x1F, 0x1F, 0x0E}; // thermometer
    uint8_t iconBat[8]   = {0x0E, 0x1B, 0x11, 0x11, 0x1F, 0x1F, 0x1F, 0x1F}; // battery
    uint8_t iconLink[8]  = {0x00, 0x00, 0x01, 0x05, 0x15, 0x15, 0x05, 0x01}; // signal
    uint8_t iconHeart[8] = {0x00, 0x0A, 0x1F, 0x1F, 0x1F, 0x0E, 0x04, 0x00}; // heart
    
    _lcd->createChar(0, iconArrow);
    _lcd->createChar(1, iconTemp);
    _lcd->createChar(2, iconBat);
    _lcd->createChar(3, iconLink);
    _lcd->createChar(4, iconHeart);
    
    clear();
  }
  
  void createCustomChar(uint8_t location, uint8_t charmap[]) { if (_lcd) _lcd->createChar(location, charmap); }
  void writeRaw(uint8_t c) { if (_lcd) _lcd->write(c); }

  void clear(){
    if (!_lcd) return;
    _lcd->clear();

    // 16x1 büyük font (8x2 adresleme) için iki yarıyı boşlukla temizle
    if (_rows == 1){
      _lcd->setCursor(0, 0);
      _lcd->print("        ");
      if (_splitRow16x1){
        _lcd->setCursor(0, 1);
      } else {
        _lcd->setCursor(8, 0);
      }
      _lcd->print("        ");
      _lcd->setCursor(0, 0);
    } else {
      _lcd->setCursor(0, 0);
    }
  }

  void printLine(const String &msg){
    if (!_lcd) return;
    String m = msg;
    if ((int)m.length() > _cols) m = m.substring(0, _cols);

    if (_rows == 1){
      // 16x1 büyük font: ilk 8 karakter satır 0'a, sonraki 8 satır 1'e yazılır
      String s0 = m.substring(0, min(8, (int)m.length()));
      while ((int)s0.length() < 8) s0 += ' ';
      String s1 = (m.length() > 8) ? m.substring(8) : String("");
      while ((int)s1.length() < 8) s1 += ' ';

      _lcd->setCursor(0, 0);
      _lcd->print(s0);
      if (_splitRow16x1){
        _lcd->setCursor(0, 1);
      } else {
        _lcd->setCursor(8, 0);
      }
      _lcd->print(s1);
      _lcd->setCursor(0, 0);
      return;
    }

    // Klasik 16x2 vb.
    _lcd->setCursor(0, 0);
    _lcd->print(m);
    for (int i = (int)m.length(); i < _cols; i++) _lcd->print(' ');
  }

  void printLines(const String &line1, const String &line2){
    if (!_lcd) return;

    if (_rows <= 1){
      // 16x1 büyük font cihazlarda ikinci satır gerçek değil; tek satıra indir.
      if (line2.length() == 0) printLine(line1);
      else printLine(line1 + " " + line2);
      return;
    }

    String a = line1;
    String b = line2;
    if ((int)a.length() > _cols) a = a.substring(0, _cols);
    if ((int)b.length() > _cols) b = b.substring(0, _cols);

    _lcd->setCursor(0, 0);
    _lcd->print(a);
    for (int i = (int)a.length(); i < _cols; i++) _lcd->print(' ');

    _lcd->setCursor(0, 1);
    _lcd->print(b);
    for (int i = (int)b.length(); i < _cols; i++) _lcd->print(' ');

    _lcd->setCursor(0, 0);
  }

  // Print up to 4 lines (for 20x4 displays). If device has fewer rows,
  // lines will be concatenated or truncated appropriately.
  void print4Lines(const String &l1, const String &l2, const String &l3, const String &l4){
    if (!_lcd) return;

    if (_rows <= 1){
      // fallback: join lines
      String combined = l1;
      if (l2.length()) combined += " " + l2;
      if (l3.length()) combined += " " + l3;
      if (l4.length()) combined += " " + l4;
      printLine(combined);
      return;
    }

    // If only 2 rows, show first two lines concatenated with the remaining as overflow
    if (_rows == 2){
      String top = l1;
      if (l2.length()) top += " " + l2;
      String bot = l3;
      if (l4.length()) bot += " " + l4;
      printLines(top, bot);
      return;
    }

    // rows >= 3: print each available line on successive rows
    String s[4] = {l1, l2, l3, l4};
    for (int r = 0; r < min(4, _rows); r++){
      String m = s[r];
      if ((int)m.length() > _cols) m = m.substring(0, _cols);
      _lcd->setCursor(0, r);
      _lcd->print(m);
      for (int i = (int)m.length(); i < _cols; i++) _lcd->print(' ');
    }
    _lcd->setCursor(0, 0);
  }

private:
  LiquidCrystal_I2C *_lcd{nullptr};
  uint8_t _addr{LCD_I2C_ADDR};
  uint8_t _cols{LCD_COLS};
  uint8_t _rows{LCD_ROWS};
  bool _splitRow16x1{(bool)LCD_16X1_SPLIT_ROW};
};
#endif

#endif // SENTRY_PERIPHERALS_LCD_DISPLAY_H
