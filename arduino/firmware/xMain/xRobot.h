#ifndef ROBOT_ROBOT_H
#define ROBOT_ROBOT_H

#include <Arduino.h>
#include <math.h>
#include "xConfig.h"
#include "xImu.h"
#include "actuators/xServoBus.h"
#include "actuators/xStepperPair.h"

enum Side { LEFT, RIGHT };
enum RobotMode { MODE_STAND, MODE_SIT };

class Robot {
public:
  void begin(){
    // Attach servos (left/right tilt+pan)
    uint8_t pins[SERVO_COUNT_TOTAL] = {PIN_L_TILT, PIN_L_PAN, PIN_R_TILT, PIN_R_PAN};
    servos.attachAll(pins, POSE_STAND);
    servos.setSpeed(SPEED_DEG_PER_S);

    // Steppers
    steppers.begin();

    // IMU
    Wire.begin();
  #if defined(ARDUINO_ARCH_AVR)
    // Prevent hard lockups on missing/bad I2C devices.
    Wire.setWireTimeout(25000, true);
  #endif
    imu.begin(IMU_I2C_ADDR);

    lastPidMs = millis();
    mode = MODE_STAND; skateBalance=false;
    // Initialize runtime-tunable gains from config
    pidKpPitch = PID_PITCH_KP; pidKiPitch = PID_PITCH_KI; pidKdPitch = PID_PITCH_KD;
    pidKpRoll  = PID_ROLL_KP;  pidKiRoll  = PID_ROLL_KI;  pidKdRoll  = PID_ROLL_KD;
    skateKp = SKATE_KP; skateKi = SKATE_KI; skateKd = SKATE_KD; skateSpeedLimit = SKATE_SPEED_LIMIT;
  }

  void update(){
    servos.update();
    steppers.update();
  }

  void head(float tilt, float pan){
    // Write tilt/pan to both left and right pairs
    servos.write(0, constrain(tilt, HEAD_TILT_MIN, HEAD_TILT_MAX));
    servos.write(1, constrain(pan,  HEAD_PAN_MIN,  HEAD_PAN_MAX));
    servos.write(2, constrain(tilt, HEAD_TILT_MIN, HEAD_TILT_MAX));
    servos.write(3, constrain(pan,  HEAD_PAN_MIN,  HEAD_PAN_MAX));
  }

  void calibrateNeutral(){ servos.writePose(POSE_STAND); }

  void setBalance(bool en){ balanceEnabled = en; }
  bool isBalanceEnabled() const { return balanceEnabled; }

  RobotMode getMode() const { return mode; }

  void estop(){
    // Detach servos and stop steppers immediately
    servos.detachAll();
    steppers.stop();
    balanceEnabled = false; skateBalance = false;
  }

  // Runtime tuning
  void setPidGains(float kpP, float kiP, float kdP, float kpR, float kiR, float kdR){
    pidKpPitch=kpP; pidKiPitch=kiP; pidKdPitch=kdP; pidKpRoll=kpR; pidKiRoll=kiR; pidKdRoll=kdR;
  }
  void setSkateGains(float kp, float ki, float kd){ skateKp=kp; skateKi=ki; skateKd=kd; }
  void setSkateSpeedLimit(float lim){ skateSpeedLimit = lim; }
  void setServoSpeed(float dps){ servos.setSpeed(dps); }

  void getPidGains(float &kpP, float &kiP, float &kdP, float &kpR, float &kiR, float &kdR) const {
    kpP=pidKpPitch; kiP=pidKiPitch; kdP=pidKdPitch; kpR=pidKpRoll; kiR=pidKiRoll; kdR=pidKdRoll;
  }
  void getSkateGains(float &kp, float &ki, float &kd) const { kp=skateKp; ki=skateKi; kd=skateKd; }
  float getSkateSpeedLimit() const { return skateSpeedLimit; }

  // Joint-limited writes
  void writeServoLimited(int index, float deg){
    float d = deg;
    switch(index){
      // 0,2 = tilt; 1,3 = pan
      case 0: case 2: d = constrain(d, HEAD_TILT_MIN, HEAD_TILT_MAX); break;
      case 1: case 3: d = constrain(d, HEAD_PAN_MIN, HEAD_PAN_MAX); break;
      default: break;
    }
    servos.write(index, d);
  }
  void writePoseLimited(const uint8_t pose[SERVO_COUNT_TOTAL]){
    for (int i=0;i<SERVO_COUNT_TOTAL;i++) writeServoLimited(i, pose[i]);
  }

  // Mode control with selective detach in Sit
  void setModeStand(){ mode = MODE_STAND; }
  void setModeSit(){ mode = MODE_SIT; }

  // Expose subsystems
  Imu imu;
  ServoBus servos;
  StepperPair steppers;
  float driveCmd = 0; // user-requested forward (+)/backward (-) velocity (steps/s)

public:
  void setDriveCmd(float v){ driveCmd = constrain(v, -skateSpeedLimit, skateSpeedLimit); }
  float getDriveCmd() const { return driveCmd; }

private:
  // PID state
  bool balanceEnabled = false;
  unsigned long lastPidMs = 0;
  float iPitch=0, iRoll=0;
  float lastPitch=0, lastRoll=0;
  RobotMode mode{MODE_STAND};
  bool skateBalance=false;
  // Runtime PID and skate gains
  float pidKpPitch=PID_PITCH_KP, pidKiPitch=PID_PITCH_KI, pidKdPitch=PID_PITCH_KD;
  float pidKpRoll =PID_ROLL_KP,  pidKiRoll =PID_ROLL_KI,  pidKdRoll =PID_ROLL_KD;
  float skateKp=SKATE_KP, skateKi=SKATE_KI, skateKd=SKATE_KD;
  float skateSpeedLimit=SKATE_SPEED_LIMIT;

  void balancePid(){
    // Balance controller disabled for pan/tilt-only configuration.
    (void)balanceEnabled; (void)lastPidMs; (void)iPitch; (void)iRoll;
    (void)lastPitch; (void)lastRoll; (void)mode; (void)skateBalance;
    // IMU still available if callers need it
    imu.read();
  }

  // Simple, smooth stand-up animation
  void playStandAnimation(){ writePoseLimited(POSE_STAND); waitUntilSettled(1500); }

  // Sit down animation (gentle fold)
  void playSitAnimation(){ writePoseLimited(POSE_SIT); waitUntilSettled(1500); }

  void waitUntilSettled(unsigned long maxMs){
    unsigned long t0 = millis();
    while (!servos.isSettled() && millis() - t0 < maxMs){
      servos.update();
      delay(5);
    }
  }
};

#endif // ROBOT_ROBOT_H