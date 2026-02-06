#ifndef ROBOT_ROBOT_H
#define ROBOT_ROBOT_H

#include <Arduino.h>
#include <math.h>
#include "xConfig.h"
#include "xImu.h"
#include "xKinematics.h"
#include "actuators/xServoBus.h"
#include "actuators/xStepperPair.h"

enum Side { LEFT, RIGHT };
enum RobotMode { MODE_STAND, MODE_SIT };

class Robot {
public:
  void begin(){
    // Attach servos
    uint8_t pins[SERVO_COUNT_TOTAL] = {PIN_L_HIP,PIN_L_KNEE,PIN_L_ANKLE, PIN_R_HIP,PIN_R_KNEE,PIN_R_ANKLE, PIN_HEAD_TILT,PIN_HEAD_PAN};
    servos.attachAll(pins, POSE_STAND);
    servos.setSpeed(SPEED_DEG_PER_S);

    // Steppers
    steppers.begin();

    // IK
    ik.setup(THIGH_LEN, SHIN_LEN);
    ik.setOffsets(OFFS_HIP, OFFS_KNEE, OFFS_ANKLE);

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
    balancePid();
  }

  // High level actions
  bool setLegByIK(Side side, float x){
    IkSolution L = ik.solve(x, 0);
    if (!L.valid) return false;
    IkSolution R; LegIK2D::mirror(L,R);
    if (side==LEFT){ setLeft(L); } else { setRight(R); }
    return true;
  }

  void setLeft(const IkSolution &s){ servos.write(0, s.hip); servos.write(1, s.knee); servos.write(2, s.ankle); }
  void setRight(const IkSolution &s){ servos.write(3, s.hip); servos.write(4, s.knee); servos.write(5, s.ankle); }

  void head(float tilt, float pan){
    servos.write(6, constrain(tilt, HEAD_TILT_MIN, HEAD_TILT_MAX));
    servos.write(7, constrain(pan,  HEAD_PAN_MIN,  HEAD_PAN_MAX));
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
      case 0: case 3: d = constrain(d, HIP_MIN, HIP_MAX); break;
      case 1: case 4: d = constrain(d, KNEE_MIN, KNEE_MAX); break;
      case 2: case 5: d = constrain(d, ANKLE_MIN, ANKLE_MAX); break;
      case 6: d = constrain(d, HEAD_TILT_MIN, HEAD_TILT_MAX); break;
      case 7: d = constrain(d, HEAD_PAN_MIN, HEAD_PAN_MAX); break;
      default: break;
    }
    servos.write(index, d);
  }
  void writePoseLimited(const uint8_t pose[SERVO_COUNT_TOTAL]){
    for (int i=0;i<SERVO_COUNT_TOTAL;i++) writeServoLimited(i, pose[i]);
  }

  // Mode control with selective detach in Sit
  void setModeStand(){
    mode = MODE_STAND; skateBalance = false; balanceEnabled = true;
    // Reattach all and play stand animation
    servos.reattachAll();
  }
  void setModeSit(){
    mode = MODE_SIT; balanceEnabled = false; skateBalance = true;
    // Detached knees/ankles (1,2,4,5); animations removed per configuration
    servos.detachOne(1); servos.detachOne(2); servos.detachOne(4); servos.detachOne(5);
    // Reset user drive
    driveCmd = 0;
  }

  // Expose subsystems
  Imu imu;
  ServoBus servos;
  StepperPair steppers;
  LegIK2D ik;
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
    unsigned long now = millis();
    if (now - lastPidMs < PID_SAMPLE_MS) return;
    lastPidMs = now;
    imu.read();
    float p = imu.getPitch();
    float r = imu.getRoll();
    // Deadband
    if (fabs(p) < PID_DEADBAND_DEG) p = 0; if (fabs(r) < PID_DEADBAND_DEG) r = 0;
    // Derivative (per-sample)
    float dp = p - lastPitch; float dr = r - lastRoll; lastPitch=p; lastRoll=r;
    // Integrator (for servo PID)
    iPitch += p; iRoll += r;

    // 1) Servo-based balance (Stand mode or when explicitly enabled)
    if (balanceEnabled){
      float outP = pidKpPitch*p + pidKiPitch*iPitch + pidKdPitch*dp;
      float outR = pidKpRoll*r  + pidKiRoll*iRoll  + pidKdRoll*dr;
      outP = constrain(outP, -PID_OUT_LIMIT, PID_OUT_LIMIT);
      outR = constrain(outR, -PID_OUT_LIMIT, PID_OUT_LIMIT);
      // Apply as corrective offsets on hip servos (0=L hip, 3=R hip)
      writeServoLimited(0, servos.get(0) - outP - outR);
      writeServoLimited(3, servos.get(3) - outP + outR);
    }

    // 2) Skate (stepper) balance in Sit mode: combine user drive with balance correction
    if (skateBalance && mode==MODE_SIT){
      float v_corr = skateKp * p + skateKd * dp; // steps/s correction
      v_corr = constrain(v_corr, -skateSpeedLimit, skateSpeedLimit);
      float v_cmd = driveCmd + v_corr;
      v_cmd = constrain(v_cmd, -skateSpeedLimit, skateSpeedLimit);
      steppers.setSpeedOne(0, v_cmd);
      steppers.setSpeedOne(1, v_cmd);
    }
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