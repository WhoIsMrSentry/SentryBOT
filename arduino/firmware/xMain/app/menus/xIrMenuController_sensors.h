// Sensors display implementations moved into menus/
#ifndef SENTRY_APP_IR_MENU_CONTROLLER_SENSORS_H
#define SENTRY_APP_IR_MENU_CONTROLLER_SENSORS_H

#if IR_ENABLED

#include "../xIrMenuController.h"

void IrMenuController::refreshLive(Robot &robot){
  if (_state == STATE_TEMPS){
    showTemperatures();
    return;
  }
  if (_state == STATE_LASER){
    showLaser();
    return;
  }

  if (_state == STATE_ULTRA){
#if ULTRA_ENABLED
    if (isnan(g_ultraCm)) lcdPrint((const __FlashStringHelper*)F("   ULTRA SENSOR   "), (const __FlashStringHelper*)F("      NO ECHO     "));
    else {
      char l1[21], l2[21], l3[21], l4[21];
      snprintf_P(l1, sizeof(l1), PSTR("   ULTRA SENSOR     "));
      snprintf_P(l2, sizeof(l2), PSTR("--------------------"));
      int whole = (int)g_ultraCm;
      int frac = (int)((g_ultraCm - whole) * 10);
      snprintf_P(l3, sizeof(l3), PSTR(" DIST: %d.%d cm     "), whole, abs(frac));
        
      // Modern progress bar
      int dots = (int)constrain(g_ultraCm / 5.0f, 0, 16);
      String bar = " [";
      for (int i=0; i<dots && i<16; i++) bar += "=";
      for (int i=dots; i<16; i++) bar += " ";
      bar += "]";
      strncpy(l4, bar.c_str(), sizeof(l4));
      l4[sizeof(l4)-1] = '\0';
      g_lcdStatus.show4To(LCD_TGT_1, l1, l2, l3, l4, true);
    }
#else
    lcdPrint("ULTRA", "DISABLED");
#endif
    return;
  }

  if (_state == STATE_RFID){
#if RFID_ENABLED
    char l1[21], l2[21], l3[21], l4[21];
    snprintf_P(l1, sizeof(l1), PSTR("    RFID READER     "));
    snprintf_P(l2, sizeof(l2), PSTR("--------------------"));
    if (g_lastRfid.length() == 0){
      snprintf_P(l3, sizeof(l3), PSTR("  STATUS: IDLE      "));
      snprintf_P(l4, sizeof(l4), PSTR("  WAITING FOR TAG   "));
    } else {
      String tail = g_lastRfid;
      if (tail.length() > 16) tail = tail.substring(tail.length() - 16);
      snprintf_P(l3, sizeof(l3), PSTR("  LAST ID:          "));
      snprintf_P(l4, sizeof(l4), PSTR("  %-16s  "), tail.c_str());
    }
    g_lcdStatus.show4To(LCD_TGT_1, l1, l2, l3, l4, true);
#else
    lcdPrint((const __FlashStringHelper*)F("RFID"), (const __FlashStringHelper*)F("DISABLED"));
#endif
    return;
  }

  if (_state == STATE_IMU){
    robot.imu.read();
    float p = robot.imu.getPitch();
    float r = robot.imu.getRoll();

    if (LCD_ROWS >= 4){
      // Plain ASCII so the page renders regardless of CGRAM state, and we use
      // signed clamps so very large IMU values cannot overflow the row width
      // (which previously truncated mid-row and gave the panel nothing to show).
      int pi  = (int)constrain(p, -999.0f, 999.0f);
      int ri  = (int)constrain(r, -999.0f, 999.0f);
      int ax  = (int)constrain(robot.imu.getAccX(), -9999.0f, 9999.0f);
      int ay  = (int)constrain(robot.imu.getAccY(), -9999.0f, 9999.0f);
      int az  = (int)constrain(robot.imu.getAccZ(), -9999.0f, 9999.0f);
      int tc  = (int)constrain(robot.imu.getTempC(), -99.0f,  150.0f);

      char l1[21], l2[21], l3[21], l4[21];
      snprintf_P(l1, sizeof(l1), PSTR("   IMU SENSOR       "));
      snprintf_P(l2, sizeof(l2), PSTR(" PITCH:%-4d ROLL:%-3d"), pi, ri);
      snprintf_P(l3, sizeof(l3), PSTR(" AX:%-4d AY:%-4d    "), ax, ay);
      snprintf_P(l4, sizeof(l4), PSTR(" AZ:%-4d  TEMP:%-3dC "), az, tc);
      g_lcdStatus.show4To(LCD_TGT_1, l1, l2, l3, l4, true);
    } else {
      if (_imuSub == 0){
        String line;
        line.reserve(24);
        line = "P:";
        line += String(p, 1);
        line += " R:";
        line += String(r, 1);
        lcdPrint("IMU", line);
      } else if (_imuSub == 1){
        String line;
        line.reserve(24);
        line = "AX:";
        line += String(robot.imu.getAccX(), 1);
        line += " AY:";
        line += String(robot.imu.getAccY(), 1);
        lcdPrint("IMU", line);
      } else {
        String line;
        line.reserve(24);
        line = "AZ:";
        line += String(robot.imu.getAccZ(), 1);
        line += " T:";
        line += String(robot.imu.getTempC(), 0);
        lcdPrint("IMU", line);
      }
    }
    return;
  }

  if (_state == STATE_SYSTEM){
    char l1[21], l2[21], l3[21], l4[21];
    
    // Line 1: Mode and Uptime with heart icon
    unsigned long upS = millis() / 1000;
    int h = upS / 3600;
    int m = (upS / 60) % 60;
    int s = upS % 60;
    snprintf_P(l1, sizeof(l1), PSTR("\x04 %s UP %02d:%02d:%02d"), (robot.getMode()==MODE_HEAD_TRACK)?"S":"K", h, m, s);
    
    // Line 2: Connectivity with link icon (Shortened labels to fit 20 chars)
    snprintf_P(l2, sizeof(l2), PSTR("\x03 S:%s R:%s RF:%s"), robot.servos.driverOk()?"OK":"NO", "NA", g_lastRfid.length()?"OK":"NO");
    
    // Line 3: IMU and Drive with temp icon (multi-purpose)
    snprintf_P(l3, sizeof(l3), PSTR("\x01 IMU:%s DRV:%d"), robot.imu.isReady()?"OK":"NO", (int)robot.getDriveCmd());
    
    // Line 4: Ultra and Misc with battery icon (simulated for now)
#if ULTRA_ENABLED
    String ul = isnan(g_ultraCm) ? "NA" : String((int)g_ultraCm);
    snprintf_P(l4, sizeof(l4), PSTR("\x02 ULTRA:%scm BTN:OK"), ul.c_str());
#else
    snprintf_P(l4, sizeof(l4), PSTR("\x02 ULTRA:OFF BTN:OK"));
#endif

    g_lcdStatus.show4To(LCD_TGT_1, l1, l2, l3, l4, true);
    return;
  }
  
  if (_state == STATE_ALERTS){
    showAlerts();
    return;
  }
  
  if (_state == STATE_STATS){
    showStats();
    return;
  }
}

#endif // IR_ENABLED

#endif // SENTRY_APP_IR_MENU_CONTROLLER_SENSORS_H
