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
    if (isnan(g_ultraCm)) lcdPrint("ULTRA", "NO ECHO");
    else {
      String line;
      line.reserve(12);
      line = String(g_ultraCm, 1);
      line += "cm";
      lcdPrint("ULTRA", line);
    }
#else
    lcdPrint("ULTRA", "DISABLED");
#endif
    return;
  }

  if (_state == STATE_RFID){
#if RFID_ENABLED
    if (g_lastRfid.length() == 0) lcdPrint("RFID", "NONE");
    else {
      String tail = g_lastRfid;
      if (tail.length() > 8) tail = tail.substring(tail.length() - 8);
      lcdPrint("RFID", tail);
    }
#else
    lcdPrint("RFID", "DISABLED");
#endif
    return;
  }

  if (_state == STATE_IMU){
    robot.imu.read();
    float p = robot.imu.getPitch();
    float r = robot.imu.getRoll();
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
    return;
  }

  if (_state == STATE_SYSTEM){
    if (_sysSub == 0){
      String top = (robot.getMode()==MODE_HEAD_TRACK) ? "SYS STAND" : "SYS SIT";
      String b;
      b.reserve(14);
      b = "DRV:";
      b += String((int)robot.getDriveCmd());
      lcdPrint(top, b);
      return;
    }

    if (_sysSub == 1){
      String a = "MOD";
    #if LCD_ENABLED
      a = String("LCD") + (g_lcd1Ok ? "1" : "-");
    #endif
      String b;
      b.reserve(8);
      b = "IMU:";
      b += (robot.imu.isReady() ? "OK" : "NO");
      lcdPrint(a, b);
      return;
    }

    // sub 2
    String b;
    b.reserve(12);
    b = "SERVO:";
    b += (robot.servos.driverOk() ? "OK" : "NO");
#if ULTRA_ENABLED
    String top = "UL:";
    if (isnan(g_ultraCm)) top += "NA";
    else top += String((int)g_ultraCm);
#else
    String top = "UL:OFF";
#endif
    lcdPrint(top, b);
    return;
  }
}

#endif // IR_ENABLED

#endif // SENTRY_APP_IR_MENU_CONTROLLER_SENSORS_H
