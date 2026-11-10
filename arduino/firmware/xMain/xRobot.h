#ifndef ROBOT_ROBOT_H
#define ROBOT_ROBOT_H

#include <Arduino.h>
#include <math.h>
#include "xConfig.h"
#include "xImu.h"
#include "actuators/xServoBus.h"
#include "actuators/xStepperPair.h"

enum RobotMode { MODE_HEAD_TRACK, MODE_SKATE };

class Robot {
public:
  void begin(){
    // Attach servos (pan, tilt, pi servo 1, pi servo 2) from PROGMEM POSE_STAND
    uint8_t pins[SERVO_COUNT_TOTAL] = {PIN_PAN, PIN_TILT, PIN_PI_SERVO_1, PIN_PI_SERVO_2};
    servos.attachAllProgmem(pins, POSE_STAND);
    servos.setSpeed(SPEED_DEG_PER_S);

    // Steppers
    steppers.begin();

    // IMU
    Wire.begin();
  #if defined(ARDUINO_ARCH_AVR)
    // Prevent hard lockups on missing/bad I2C devices and auto-recover the
    // bus so an unhealthy IMU does not silently break LCD/PCA9685 traffic.
    Wire.setWireTimeout(I2C_WIRE_TIMEOUT_US, true);
  #endif
    imu.begin(IMU_I2C_ADDR);

    _estopped = false;
    _driveActive = false;
    mode = MODE_HEAD_TRACK;
    // Skate gains initialized from config
    skateKp = SKATE_KP; skateKi = SKATE_KI; skateKd = SKATE_KD; skateSpeedLimit = SKATE_SPEED_LIMIT;
  }

  void update(){
    servos.update();
    if (!_estopped && mode == MODE_SKATE && _driveActive){
      float pitch = imu.isReady() ? imu.getPitch() : 0.0f;
      float bal = (fabs(pitch) > 2.0f) ? (skateKp * pitch) : 0.0f;
      float spd = constrain(driveCmd + bal, -skateSpeedLimit, skateSpeedLimit);
      steppers.setSpeed(spd, spd);
    }
    steppers.update();
  }

  void head(float tilt, float pan){
    // Pan/Tilt are single servos
    servos.write(0, constrain(pan,  PAN_MIN,  PAN_MAX));
    servos.write(1, constrain(tilt, TILT_MIN, TILT_MAX));
  }

  void calibrateNeutral(){ servos.writePoseProgmem(POSE_STAND); }

  RobotMode getMode() const { return mode; }
  bool isEstopped() const { return _estopped; }

  void estop(){
    // Latches E-STOP across servos, steppers, ramps, PID, and drive state
    _estopped = true;
    _driveActive = false;
    driveCmd = 0.0f;
    servos.detachAll();
    steppers.stop();
    steppers.stopAllRamps();
    steppers.disableAllPid();
    steppers.setEnable(false);
  }

  void clearEstop(){
    _estopped = false;
    _driveActive = false;
    driveCmd = 0.0f;
    steppers.setEnable(true);
    servos.reattachAll();
  }

  // Runtime tuning
  void setSkateGains(float kp, float ki, float kd){ skateKp=kp; skateKi=ki; skateKd=kd; }
  void setSkateSpeedLimit(float lim){ if (lim > 0.0f) skateSpeedLimit = lim; }
  void setServoSpeed(float dps){ servos.setSpeed(dps); }

  void getSkateGains(float &kp, float &ki, float &kd) const { kp=skateKp; ki=skateKi; kd=skateKd; }
  float getSkateSpeedLimit() const { return skateSpeedLimit; }

  // Joint-limited writes
  void writeServoLimited(int index, float deg){
    float d = deg;
    switch(index){
      // 0 = pan, 1 = tilt
      case 0: d = constrain(d, PAN_MIN,  PAN_MAX);  break;
      case 1: d = constrain(d, TILT_MIN, TILT_MAX); break;
      default: break;
    }
    servos.write(index, d);
  }
  void writePoseLimited(const uint8_t pose[SERVO_COUNT_TOTAL]){
    for (int i=0;i<SERVO_COUNT_TOTAL;i++) writeServoLimited(i, pose[i]);
  }

  // Mode control with selective detach in Sit
  // Backward-compatible API names; internal mode names are hardware-oriented.
  void setModeStand(){ mode = MODE_HEAD_TRACK; }
  void setModeSit(){ mode = MODE_SKATE; }

  // Expose subsystems
  Imu imu;
  ServoBus servos;
  StepperPair steppers;
  float driveCmd = 0; // user-requested forward (+)/backward (-) velocity (steps/s)

public:
  void setDriveCmd(float v){
    driveCmd = constrain(v, -skateSpeedLimit, skateSpeedLimit);
    if (fabs(driveCmd) > 0.1f) {
      _driveActive = true;
    } else {
      _driveActive = false;
      if (!_estopped && mode == MODE_SKATE) steppers.stop();
    }
  }
  float getDriveCmd() const { return driveCmd; }

private:
  bool _estopped{false};
  bool _driveActive{false};
  RobotMode mode{MODE_HEAD_TRACK};
  // Runtime skate gains
  float skateKp=SKATE_KP, skateKi=SKATE_KI, skateKd=SKATE_KD;
  float skateSpeedLimit=SKATE_SPEED_LIMIT;
  // IMU remains available for telemetry.
};

#endif // ROBOT_ROBOT_H