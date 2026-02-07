#ifndef ROBOT_STEPPER_PAIR_H
#define ROBOT_STEPPER_PAIR_H

#include <Arduino.h>
#include <AccelStepper.h>
#include "../xConfig.h"

class StepperPair {
public:
  void begin(){
    s1 = AccelStepper(AccelStepper::DRIVER, PIN_STEPPER1_STEP, PIN_STEPPER1_DIR);
    s2 = AccelStepper(AccelStepper::DRIVER, PIN_STEPPER2_STEP, PIN_STEPPER2_DIR);
    s1.setMaxSpeed(2000); s1.setAcceleration(1000);
    s2.setMaxSpeed(2000); s2.setAcceleration(1000);
    mode1 = MODE_POS; mode2 = MODE_POS;
    // Configure limit pins if available
    if (PIN_LIMIT1>=0){ pinMode(PIN_LIMIT1, LIMIT_ACTIVE_LOW?INPUT_PULLUP:INPUT); }
    if (PIN_LIMIT2>=0){ pinMode(PIN_LIMIT2, LIMIT_ACTIVE_LOW?INPUT_PULLUP:INPUT); }
    // Ensure step/dir pins are outputs for raw stepping
    pinMode(PIN_STEPPER1_STEP, OUTPUT);
    pinMode(PIN_STEPPER1_DIR, OUTPUT);
    pinMode(PIN_STEPPER2_STEP, OUTPUT);
    pinMode(PIN_STEPPER2_DIR, OUTPUT);
  }
  void setMaxSpeed(float v){ s1.setMaxSpeed(v); s2.setMaxSpeed(v); }
  void setAcceleration(float a){ s1.setAcceleration(a); s2.setAcceleration(a); }

  void moveTo(long p1, long p2){ s1.moveTo(p1); s2.moveTo(p2); }
  void moveBy(long d1, long d2){ s1.move(d1); s2.move(d2); }
  void setSpeed(float v1, float v2){ mode1=MODE_VEL; mode2=MODE_VEL; s1.setSpeed(v1); s2.setSpeed(v2); }

  // Single-stepper helpers (renamed to avoid overload ambiguity)
  void setModeOne(uint8_t id, bool vel){ if(id==0) mode1 = vel?MODE_VEL:MODE_POS; else mode2 = vel?MODE_VEL:MODE_POS; }
  void setSpeedOne(uint8_t id, float v){ if(id==0){ mode1=MODE_VEL; s1.setSpeed(v);} else { mode2=MODE_VEL; s2.setSpeed(v);} }
  void moveToOne(uint8_t id, long p){ if(id==0){ mode1=MODE_POS; s1.moveTo(p);} else { mode2=MODE_POS; s2.moveTo(p);} }
  void moveByOne(uint8_t id, long d){ if(id==0){ mode1=MODE_POS; s1.move(d);} else { mode2=MODE_POS; s2.move(d);} }

  // Start a non-blocking ramped drive for one stepper using raw DIR/STEP toggles.
  // direction: +1 forward, -1 backward. initialDelay/minDelay in microseconds.
  void startRampedDrive(uint8_t id, int direction, unsigned long initialDelayUs, unsigned long minDelayUs, float ivme, long fullSteps){
    if (id > 1) return;
    Ramp &r = ramps[id];
    r.active = true;
    r.dir = (direction >= 0) ? HIGH : LOW;
    r.currentDelay = (float)initialDelayUs;
    r.minDelay = (float)minDelayUs;
    r.ivme = ivme;
    r.remainingFullSteps = fullSteps;
    r.stepState = false;
    r.nextToggleMicros = micros() + (unsigned long)r.currentDelay;
    // set dir pin
    if (id == 0) digitalWrite(PIN_STEPPER1_DIR, r.dir); else digitalWrite(PIN_STEPPER2_DIR, r.dir);
    // stop AccelStepper motion for this motor while raw ramping
    if (id == 0) { mode1 = MODE_POS; s1.setSpeed(0); } else { mode2 = MODE_POS; s2.setSpeed(0); }
  }

  // Enkoder yok: yazılımsal hız kontrolü (PID-benzeri) using step timing estimator.
  void setPidGains(uint8_t id, float kp, float ki, float kd){ if(id>1) return; pidCtrls[id].kp=kp; pidCtrls[id].ki=ki; pidCtrls[id].kd=kd; }
  void getPidGains(uint8_t id, float &kp, float &ki, float &kd){ if (id>1) {kp=ki=kd=0; return;} kp=pidCtrls[id].kp; ki=pidCtrls[id].ki; kd=pidCtrls[id].kd; }
  void startPidControl(uint8_t id, float targetHz){ if(id>1) return; pidCtrls[id].enabled=true; pidCtrls[id].targetHz=targetHz; pidCtrls[id].integral=0; pidCtrls[id].lastError=0; pidCtrls[id].lastUpdateMicros=micros(); }
  void stopPidControl(uint8_t id){ if(id>1) return; pidCtrls[id].enabled=false; }

  void stopRampedDrive(uint8_t id){ if (id>1) return; ramps[id].active = false; }

  void update(){
    unsigned long now = micros();
    // Handle ramping first; if ramp active for a motor, drive raw toggles instead of AccelStepper
    for (int i=0;i<2;i++){
      Ramp &r = ramps[i];
      if (!r.active) continue;
      if ((long)(now - r.nextToggleMicros) >= 0){
        // toggle step pin
        int stepPin = (i==0)?PIN_STEPPER1_STEP:PIN_STEPPER2_STEP;
        digitalWrite(stepPin, r.stepState?LOW:HIGH);
        r.stepState = !r.stepState;
        if (!r.stepState){
          // completed a full step (HIGH then LOW)
          if (r.remainingFullSteps > 0) r.remainingFullSteps--;
        }
        // update delay/ramp
        if (r.currentDelay > r.minDelay){ r.currentDelay *= r.ivme; if (r.currentDelay < r.minDelay) r.currentDelay = r.minDelay; }
        else {
          // at min speed; check remaining steps
          if (r.remainingFullSteps <= 0){ r.active = false; }
        }
        r.nextToggleMicros = micros() + (unsigned long)r.currentDelay;
        // record step time into estimator on full-step completion
        if (!r.stepState){ // completed a full step (after toggle low)
          recordStepTime(i, micros());
        }
      }
    }

    // For motors not in raw ramp mode, use AccelStepper as before
    if (!ramps[0].active){ if (mode1==MODE_VEL) s1.runSpeed(); else s1.run(); }
    if (!ramps[1].active){ if (mode2==MODE_VEL) s2.runSpeed(); else s2.run(); }

    // PID loop: adjust delay for PID-controlled motors (if not using AccelStepper raw mode)
    for (int i=0;i<2;i++){
      if (!pidCtrls[i].enabled) continue;
      pidStepControl(i);
    }
  }

  long pos1() const { return s1.currentPosition(); }
  long pos2() const { return s2.currentPosition(); }

  void stop(){
    // Immediate velocity stop; keep modes in velocity for safety
    mode1 = MODE_VEL; mode2 = MODE_VEL;
    s1.setSpeed(0); s2.setSpeed(0);
  }

  void zeroNow(){ s1.setCurrentPosition(0); s2.setCurrentPosition(0); }
  void zeroSet(long p1, long p2){ s1.setCurrentPosition(p1); s2.setCurrentPosition(p2); }

  // Blocking simple homing towards negative direction until limit switch is hit
  void homeBoth(long speed = -400){
    if (PIN_LIMIT1<0 && PIN_LIMIT2<0) return;
    s1.setSpeed(speed); s2.setSpeed(speed);
    mode1 = MODE_VEL; mode2 = MODE_VEL;
    while (true){
      if (PIN_LIMIT1>=0){ if (digitalRead(PIN_LIMIT1)==(LIMIT_ACTIVE_LOW?LOW:HIGH)) { s1.setSpeed(0); s1.setCurrentPosition(0); } }
      if (PIN_LIMIT2>=0){ if (digitalRead(PIN_LIMIT2)==(LIMIT_ACTIVE_LOW?LOW:HIGH)) { s2.setSpeed(0); s2.setCurrentPosition(0); } }
      if ((PIN_LIMIT1<0 || s1.speed()==0) && (PIN_LIMIT2<0 || s2.speed()==0)) break;
      s1.runSpeed(); s2.runSpeed();
      delay(2);
    }
  }

private:
  AccelStepper s1{AccelStepper::DRIVER, PIN_STEPPER1_STEP, PIN_STEPPER1_DIR};
  AccelStepper s2{AccelStepper::DRIVER, PIN_STEPPER2_STEP, PIN_STEPPER2_DIR};
  enum Mode { MODE_POS, MODE_VEL };
  Mode mode1{MODE_POS}, mode2{MODE_POS};
  struct Ramp {
    bool active{false};
    int dir{HIGH};
    unsigned long nextToggleMicros{0};
    float currentDelay{0.0f};
    float minDelay{0.0f};
    float ivme{0.995f};
    long remainingFullSteps{0};
    bool stepState{false};
  };
  Ramp ramps[2];

  // --- PID-like velocity controller (works without encoder) ---
  struct PidCtrl {
    bool enabled{false};
    float kp{0.1f}, ki{0.01f}, kd{0.0f};
    float integral{0.0f};
    float lastError{0.0f};
    unsigned long lastUpdateMicros{0};
    float targetHz{0.0f};
    // estimator ring buffer (timestamps of recent full steps)
    static const int EST_N = 8;
    unsigned long stamps[EST_N]{0};
    int si{0};
    int count{0};
  };
  PidCtrl pidCtrls[2];

  // Record a completed full step timestamp for estimator
  void recordStepTime(int id, unsigned long t){ if (id<0||id>1) return; PidCtrl &p = pidCtrls[id]; p.stamps[p.si++] = t; if (p.si>=PidCtrl::EST_N) p.si=0; if (p.count < PidCtrl::EST_N) p.count++; }

  // Compute estimated Hz (full steps/sec) from stamps
  float estimateHz(int id){ PidCtrl &p = pidCtrls[id]; if (p.count < 2) return 0.0f; int earliest = (p.si + PidCtrl::EST_N - p.count) % PidCtrl::EST_N; unsigned long t0 = p.stamps[earliest]; unsigned long t1 = p.stamps[(p.si + PidCtrl::EST_N -1) % PidCtrl::EST_N]; unsigned long dt = (t1>t0)?(t1 - t0):1; float secs = (float)dt / 1000000.0f; return (float)(p.count - 1) / secs; }

  // PID step control: adjust raw-delay to track targetHz. This function nudges ramps[i].currentDelay when PID enabled.
  void pidStepControl(int id){ if (id<0||id>1) return; PidCtrl &p = pidCtrls[id]; unsigned long now = micros(); float hz = estimateHz(id);
    float error = p.targetHz - hz;
    float dt = (p.lastUpdateMicros==0)?( (float)(now - now) / 1000000.0f ) : (float)(now - p.lastUpdateMicros) / 1000000.0f;
    if (dt <= 0) dt = 1e-6f;
    p.integral += error * dt;
    float deriv = (error - p.lastError) / dt;
    float out = p.kp * error + p.ki * p.integral + p.kd * deriv;
    p.lastError = error; p.lastUpdateMicros = now;
    // Map output (Hz delta) into delay space; compute adjusted targetHz
    float adjHz = p.targetHz + out;
    if (adjHz < 0.5f) adjHz = 0.5f; // avoid div0
    float newDelayUs = 1000000.0f / (2.0f * adjHz); // micros per half-toggle
    // Constrain by ramp min/max typical values
    float minAllowed = 500.0f; // 500us half-toggle ~= 1000 full-steps/s
    float maxAllowed = 20000.0f; // 20ms half-toggle
    if (newDelayUs < minAllowed) newDelayUs = minAllowed;
    if (newDelayUs > maxAllowed) newDelayUs = maxAllowed;
    // If a raw ramp is active, respect its minDelay as lower bound
    if (ramps[id].active){ if (newDelayUs < ramps[id].minDelay) newDelayUs = ramps[id].minDelay; }
    ramps[id].currentDelay = newDelayUs;
  }
};

#endif // ROBOT_STEPPER_PAIR_H