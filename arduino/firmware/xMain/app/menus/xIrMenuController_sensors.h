// Sensors display implementations moved into menus/
#ifndef SENTRY_APP_IR_MENU_CONTROLLER_SENSORS_H
#define SENTRY_APP_IR_MENU_CONTROLLER_SENSORS_H

#if VIRTUAL_MENU_ENABLED

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
        
      // Fixed-buffer progress bar (avoids heap allocation)
      int dots = (int)constrain(g_ultraCm / 5.0f, 0, 16);
      l4[0] = ' '; l4[1] = '[';
      for (int i=0; i<16; i++) l4[2 + i] = (i < dots) ? '=' : ' ';
      l4[18] = ']'; l4[19] = '\0';
      lcdHubShow4(l1, l2, l3, l4);
    }
#else
    lcdPrint(F("ULTRA"), F("DISABLED"));
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
      const char *uidPtr = g_lastRfid.c_str();
      size_t ulen = g_lastRfid.length();
      if (ulen > 16) uidPtr += (ulen - 16);
      snprintf_P(l3, sizeof(l3), PSTR("  LAST ID:          "));
      snprintf_P(l4, sizeof(l4), PSTR("  %-16s  "), uidPtr);
    }
    lcdHubShow4(l1, l2, l3, l4);
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
      lcdHubShow4(l1, l2, l3, l4);
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
    
    // Line 2: Connectivity with link icon
#if RFID_ENABLED
    const char *rfOk = g_lastRfid.length() ? "OK" : "NO";
#else
    const char *rfOk = "OFF";
#endif
    snprintf_P(l2, sizeof(l2), PSTR("\x03 S:%s E:%s RF:%s"), robot.servos.driverOk()?"OK":"NO", robot.isEstopped()?"1":"0", rfOk);
    
    // Line 3: IMU and Drive with temp icon
    snprintf_P(l3, sizeof(l3), PSTR("\x01 IMU:%s DRV:%d"), robot.imu.isReady()?"OK":"NO", (int)robot.getDriveCmd());
    
    // Line 4: Ultra
#if ULTRA_ENABLED
    char ulBuf[8];
    if (isnan(g_ultraCm)) strcpy_P(ulBuf, PSTR("NA"));
    else itoa((int)g_ultraCm, ulBuf, 10);
    snprintf_P(l4, sizeof(l4), PSTR("\x02 ULTRA:%scm BTN:OK"), ulBuf);
#else
    snprintf_P(l4, sizeof(l4), PSTR("\x02 ULTRA:OFF BTN:OK"));
#endif

    lcdHubShow4(l1, l2, l3, l4);
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

#endif // VIRTUAL_MENU_ENABLED

#endif // SENTRY_APP_IR_MENU_CONTROLLER_SENSORS_H
