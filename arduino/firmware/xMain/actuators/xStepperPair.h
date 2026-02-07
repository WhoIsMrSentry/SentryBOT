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
      }
    }

    // For motors not in raw ramp mode, use AccelStepper as before
    if (!ramps[0].active){ if (mode1==MODE_VEL) s1.runSpeed(); else s1.run(); }
    if (!ramps[1].active){ if (mode2==MODE_VEL) s2.runSpeed(); else s2.run(); }
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
};

#endif // ROBOT_STEPPER_PAIR_H