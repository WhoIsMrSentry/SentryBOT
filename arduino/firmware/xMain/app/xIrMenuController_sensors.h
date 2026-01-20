#ifndef SENTRY_APP_IR_MENU_CONTROLLER_SENSORS_H
#define SENTRY_APP_IR_MENU_CONTROLLER_SENSORS_H

#if IR_ENABLED

#include "xIrMenuController.h"

void IrMenuController::refreshLive(Robot &robot){
  if (_state == STATE_LASER){
    showLaser();
    return;
  }

  if (_state == STATE_ULTRA){
#if ULTRA_ENABLED
    if (isnan(g_ultraCm)) lcdPrint("ULTRA", "NO ECHO");
    else lcdPrint("ULTRA", String(g_ultraCm, 1) + "cm");
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
      lcdPrint("IMU", "P:" + String(p, 1) + " R:" + String(r, 1));
    } else if (_imuSub == 1){
      lcdPrint("IMU", "AX:" + String(robot.imu.getAccX(), 1) + " AY:" + String(robot.imu.getAccY(), 1));
    } else {
      lcdPrint("IMU", "AZ:" + String(robot.imu.getAccZ(), 1) + " T:" + String(robot.imu.getTempC(), 0));
    }
    return;
  }

  if (_state == STATE_SYSTEM){
    if (_sysSub == 0){
      String top = (robot.getMode()==MODE_STAND) ? "SYS STAND" : "SYS SIT";
      String b = String("DRV:") + String((int)robot.getDriveCmd());
      if (robot.isBalanceEnabled()) b += " PID";
      lcdPrint(top, b);
      return;
    }

    if (_sysSub == 1){
      String a = "MOD";
#if LCD_ENABLED
      a = String("LCD") + (g_lcd1Ok ? "1" : "-");
#if LCD2_ENABLED
      a += (g_lcd2Ok ? "2" : "-");
#endif
#endif
      String b = String("IMU:") + (robot.imu.isReady() ? "OK" : "NO");
      lcdPrint(a, b);
      return;
    }

    // sub 2
    String b = String("SERVO:") + (robot.servos.driverOk() ? "OK" : "NO");
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
