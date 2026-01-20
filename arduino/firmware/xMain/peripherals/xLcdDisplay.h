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
    clear();
  }

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

private:
  LiquidCrystal_I2C *_lcd{nullptr};
  uint8_t _addr{LCD_I2C_ADDR};
  uint8_t _cols{LCD_COLS};
  uint8_t _rows{LCD_ROWS};
  bool _splitRow16x1{(bool)LCD_16X1_SPLIT_ROW};
};
#endif

#endif // SENTRY_PERIPHERALS_LCD_DISPLAY_H
