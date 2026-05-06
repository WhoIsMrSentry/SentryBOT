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
    // Attach servos (pan, tilt, pi servo 1, pi servo 2)
    uint8_t pins[SERVO_COUNT_TOTAL] = {PIN_PAN, PIN_TILT, PIN_PI_SERVO_1, PIN_PI_SERVO_2};
    servos.attachAll(pins, POSE_STAND);
    servos.setSpeed(SPEED_DEG_PER_S);

    // Steppers
    steppers.begin();

    // IMU
    Wire.begin();
  #if defined(ARDUINO_ARCH_AVR)
    // Prevent hard lockups on missing/bad I2C devices and auto-recover the
    // bus so an unhealthy IMU does not silently break LCD/PCA9685 traffic.
    Wire.setWireTimeout(25000, true);
  #endif
    imu.begin(IMU_I2C_ADDR);

    lastPidMs = millis();
    mode = MODE_HEAD_TRACK;
    // Skate gains initialized from config
    skateKp = SKATE_KP; skateKi = SKATE_KI; skateKd = SKATE_KD; skateSpeedLimit = SKATE_SPEED_LIMIT;
  }

  void update(){
    servos.update();
    steppers.update();
  }

  void head(float tilt, float pan){
    // Pan/Tilt are single servos
    servos.write(0, constrain(pan,  PAN_MIN,  PAN_MAX));
    servos.write(1, constrain(tilt, TILT_MIN, TILT_MAX));
  }

  void calibrateNeutral(){ servos.writePose(POSE_STAND); }

  RobotMode getMode() const { return mode; }

  void estop(){
    // Detach servos and stop steppers immediately
    servos.detachAll();
    steppers.stop();
  }
  // Runtime tuning
  void setSkateGains(float kp, float ki, float kd){ skateKp=kp; skateKi=ki; skateKd=kd; }
  void setSkateSpeedLimit(float lim){ skateSpeedLimit = lim; }
  void setServoSpeed(float dps){ servos.setSpeed(dps); }

  void getPidGains(float &kpP, float &kiP, float &kdP, float &kpR, float &kiR, float &kdR) const {
    // Return configured constants for compatibility with existing host calls.
    kpP = PID_PITCH_KP; kiP = PID_PITCH_KI; kdP = PID_PITCH_KD;
    kpR = PID_ROLL_KP;  kiR = PID_ROLL_KI;  kdR = PID_ROLL_KD;
  }
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
  void setDriveCmd(float v){ driveCmd = constrain(v, -skateSpeedLimit, skateSpeedLimit); }
  float getDriveCmd() const { return driveCmd; }

private:
  unsigned long lastPidMs = 0;
  RobotMode mode{MODE_HEAD_TRACK};
  // Runtime skate gains
  float skateKp=SKATE_KP, skateKi=SKATE_KI, skateKd=SKATE_KD;
  float skateSpeedLimit=SKATE_SPEED_LIMIT;
  // IMU remains available for telemetry.
};

#endif // ROBOT_ROBOT_H