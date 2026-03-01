#ifndef ROBOT_STEPPER_PAIR_H
#define ROBOT_STEPPER_PAIR_H

#include <Arduino.h>
#include <AccelStepper.h>
#include "../xConfig.h"
#include "../peripherals/xHallEncoder.h"
#include <EEPROM.h>

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
    // Enable pin (shared) if defined
    #if defined(PIN_STEPPER_ENABLE) && PIN_STEPPER_ENABLE >= 0
      pinMode(PIN_STEPPER_ENABLE, OUTPUT);
      // default to enabled
      setEnable(true);
    #endif
    // initialize PID timestamps and movement tracker
    for (int i=0;i<2;i++){ _pid[i].lastMs = millis(); _pid[i].lastCount = 0; _lastMovementMs[i] = millis(); }
  }
  void setMaxSpeed(float v){ s1.setMaxSpeed(v); s2.setMaxSpeed(v); }
  void setAcceleration(float a){ s1.setAcceleration(a); s2.setAcceleration(a); }

  void moveTo(long p1, long p2){ s1.moveTo(p1); s2.moveTo(p2); }
  void moveBy(long d1, long d2){ s1.move(d1); s2.move(d2); }
  void setSpeed(float v1, float v2){
    mode1=MODE_VEL; mode2=MODE_VEL;
    if (_pid[0].enabled && _hall[0]) { _pid[0].targetSpeed = v1; }
    else { s1.setSpeed(v1); }
    if (_pid[1].enabled && _hall[1]) { _pid[1].targetSpeed = v2; }
    else { s2.setSpeed(v2); }
  }

  // Single-stepper helpers (renamed to avoid overload ambiguity)
  void setModeOne(uint8_t id, bool vel){ if(id==0) mode1 = vel?MODE_VEL:MODE_POS; else mode2 = vel?MODE_VEL:MODE_POS; }
  void setSpeedOne(uint8_t id, float v){
    if (id==0){ mode1=MODE_VEL; if (_pid[0].enabled && _hall[0]) _pid[0].targetSpeed = v; else s1.setSpeed(v); }
    else { mode2=MODE_VEL; if (_pid[1].enabled && _hall[1]) _pid[1].targetSpeed = v; else s2.setSpeed(v); }
  }
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

  // Legacy encoderless PID support removed — use Hall encoder closed-loop instead.

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
          // legacy estimator removed
        }
      }
    }
    // For motors not in raw ramp mode, use AccelStepper as before
    if (!ramps[0].active){ if (mode1==MODE_VEL) s1.runSpeed(); else s1.run(); }
    if (!ramps[1].active){ if (mode2==MODE_VEL) s2.runSpeed(); else s2.run(); }

    // If hall encoders are attached, update them here (non-blocking)
    for (int i=0;i<2;i++){
      if (_hall[i]) _hall[i]->update();
    }

    // Closed-loop PID speed control using Hall encoder feedback
    unsigned long nowMs = millis();
    for (int i=0;i<2;i++){
      if (!_pid[i].enabled) continue;
      if (!_hall[i]) continue; // need encoder to run closed-loop
      // ensure motors are enabled
      if (!isEnabled()) { _pid[i].integral = 0.0f; _pid[i].lastError = 0.0f; continue; }
      unsigned long dt = nowMs - _pid[i].lastMs;
      if (dt < (unsigned long)STEPPER_PID_INTERVAL_MS) continue;
      unsigned long countNow = _hall[i]->getCount();
      unsigned long dCount = countNow - _pid[i].lastCount;
      // Movement detection: update lastMovementMs when pulses observed
      if (dCount >= (unsigned long)STEPPER_STALL_MIN_PULSES_PER_INTERVAL){ _lastMovementMs[i] = nowMs; _stalled[i] = false; }
      float pulsesPerSec = 0.0f;
      if (dt > 0) pulsesPerSec = ((float)dCount) * 1000.0f / (float)dt;
      float measuredStepsPerSec = pulsesPerSec * stepsPerHallPulse(i);

      float error = _pid[i].targetSpeed - measuredStepsPerSec;
      float dtSec = (float)dt / 1000.0f;
      // Integrator with anti-windup clamp
      _pid[i].integral += error * dtSec;
      if (_pid[i].integral > STEPPER_PID_INTEGRAL_LIMIT) _pid[i].integral = STEPPER_PID_INTEGRAL_LIMIT;
      if (_pid[i].integral < -STEPPER_PID_INTEGRAL_LIMIT) _pid[i].integral = -STEPPER_PID_INTEGRAL_LIMIT;
      float derivative = 0.0f;
      if (dtSec > 0.0f) derivative = (error - _pid[i].lastError) / dtSec;

      float out = _pid[i].kp * error + _pid[i].ki * _pid[i].integral + _pid[i].kd * derivative;
      // Clamp output to allowed speed range
      float outLimit = (float)STEPPER_PID_MAX_OUTPUT;
      if (out > outLimit) out = outLimit;
      if (out < -outLimit) out = -outLimit;

      // Apply to AccelStepper as commanded speed (steps/sec). If motor currently in raw ramp mode, skip.
      if (!ramps[i].active){
        if (i==0) s1.setSpeed(out); else s2.setSpeed(out);
        // if in velocity mode, runSpeed() will use this speed in the next section
      }

      // Persist last state for next iteration
      _pid[i].lastError = error;
      _pid[i].lastCount = countNow;
      _pid[i].lastMs = nowMs;

      // Stall detection: if we have a non-zero target but no movement for timeout, declare stall
      if (fabs(_pid[i].targetSpeed) > 1.0f){
        if ((long)(nowMs - _lastMovementMs[i]) > (long)STEPPER_STALL_TIMEOUT_MS){
          _stalled[i] = true;
          // Disable PID and stop motors to be safe
          _pid[i].enabled = false;
          if (!ramps[0].active && !ramps[1].active){ setEnable(false); }
          if (i==0) s1.setSpeed(0); else s2.setSpeed(0);
          // Emit a host-visible stall event so the controller can react
          SERIAL_IO.println(String("{\"evt\":\"stall\",\"id\":") + String(i) + String("}"));
        }
      }
    }
  }

  // Attach a hall encoder instance to a stepper (id 0 or 1)
  void attachHallEncoder(uint8_t id, HallEncoder* h){ if (id>1) return; _hall[id]=h; }
  void attachHallEncoders(HallEncoder* h0, HallEncoder* h1){ _hall[0]=h0; _hall[1]=h1; }

  long pos1() const { return s1.currentPosition(); }
  long pos2() const { return s2.currentPosition(); }

  void stop(){
    // Immediate velocity stop; keep modes in velocity for safety
    mode1 = MODE_VEL; mode2 = MODE_VEL;
    s1.setSpeed(0); s2.setSpeed(0);
  }

  // Enable/disable stepper outputs (shared enable pin)
  void setEnable(bool en){
    _enabled = en;
    #if defined(PIN_STEPPER_ENABLE) && PIN_STEPPER_ENABLE >= 0
      bool activeLow = (bool)STEPPER_ENABLE_ACTIVE_LOW;
      if (activeLow) digitalWrite(PIN_STEPPER_ENABLE, en?LOW:HIGH);
      else digitalWrite(PIN_STEPPER_ENABLE, en?HIGH:LOW);
    #endif
  }

  bool isEnabled() const { return _enabled; }

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

  // Optional hardware hall encoders attached to each stepper (or nullptr)
  HallEncoder* _hall[2]{nullptr, nullptr};
  bool _enabled{true};
  
  // PID state per motor for closed-loop speed control
  struct PidState {
    bool enabled{false};
    float kp{STEPPER_PID_KP}, ki{STEPPER_PID_KI}, kd{STEPPER_PID_KD};
    float integral{0.0f};
    float lastError{0.0f};
    unsigned long lastMs{0};
    unsigned long lastCount{0};
    float targetSpeed{0.0f}; // steps per second
  };
  PidState _pid[2];
  // Stall detection flags and last movement timestamp
  bool _stalled[2]{false,false};
  unsigned long _lastMovementMs[2]{0,0};
  
public:
  // Convert: how many motor/output steps correspond to one hall pulse for given id
  float stepsPerHallPulse(uint8_t id) const {
    float ppr = (id==0) ? (float)HALL_PULSES_PER_REV_0 : (float)HALL_PULSES_PER_REV_1;
    if (ppr <= 0.0f) ppr = 1.0f;
    return STEPPER_STEPS_PER_REV / ppr;
  }

  // Convert hall pulses to stepper steps (rounded)
  long hallPulsesToSteps(uint8_t id, long pulses) const {
    float sp = stepsPerHallPulse(id);
    return (long)round((double)pulses * (double)sp);
  }

  // Configure PID gains for a motor
  void configurePid(uint8_t id, float kp, float ki, float kd){ if (id>1) return; _pid[id].kp=kp; _pid[id].ki=ki; _pid[id].kd=kd; }
  // Enable/disable closed-loop PID for a motor
  void enablePid(uint8_t id, bool en){ if (id>1) return; _pid[id].enabled = en; if(en){ _pid[id].lastMs = millis(); _pid[id].lastCount = (_hall[id])? _hall[id]->getCount() : 0; _pid[id].integral = 0; _pid[id].lastError=0; _lastMovementMs[id] = millis(); _stalled[id]=false; } }
  // Set desired speed (steps/s) for closed-loop; also enables PID for that motor.
  // If PID was previously disabled, reinitialize its internal state similar to enablePid(..., true).
  void setTargetSpeed(uint8_t id, float stepsPerSec){
    if (id>1) return;
    bool wasEnabled = _pid[id].enabled;
    _pid[id].targetSpeed = stepsPerSec;
    if (!wasEnabled) {
      _pid[id].lastMs    = millis();
      _pid[id].lastCount = (_hall[id]) ? _hall[id]->getCount() : 0;
      _pid[id].integral  = 0.0f;
      _pid[id].lastError = 0.0f;
    }
    _pid[id].enabled = true;
    _lastMovementMs[id] = millis();
    _stalled[id] = false;
  }
  // Stop closed-loop control for a motor
  void stopPid(uint8_t id){ if (id>1) return; _pid[id].enabled = false; }

  // Get last measured speed (steps/s) using hall counts (non-smoothed instantaneous)
  float getMeasuredSpeed(uint8_t id) {
    if (id>1) return 0.0f;
    // Not super precise here; call only for diagnostics. Returns 0 if no hall attached.
    if (!_hall[id]) return 0.0f;
    // Note: this function is lightweight and uses lastCount/lastMs from PID state, but may be stale.
    unsigned long now = millis();
    unsigned long cnt = _hall[id]->getCount();
    unsigned long dt = (now - _pid[id].lastMs);
    if (dt == 0) return 0.0f;
    unsigned long dcnt = (cnt - _pid[id].lastCount);
    float pulsesPerSec = ((float)dcnt) * 1000.0f / (float)dt;
    float stepsPerSec = pulsesPerSec * stepsPerHallPulse(id);
    return stepsPerSec;
  }

  // Read PID gains
  void getPidGains(uint8_t id, float &kp, float &ki, float &kd){ if (id>1) {kp=ki=kd=0; return;} kp=_pid[id].kp; ki=_pid[id].ki; kd=_pid[id].kd; }
  // Read PID target
  float getPidTarget(uint8_t id){ if (id>1) return 0.0f; return _pid[id].targetSpeed; }

  // Stall management
  bool isStalled(uint8_t id) const { if (id>1) return false; return _stalled[id]; }
  void clearStall(uint8_t id){ if (id>1) return; _stalled[id]=false; /* re-enable system */ setEnable(true); }

  // Persist PID gains to EEPROM for motor id
  void savePidToEeprom(uint8_t id){ if (id>1) return; EEPROM.update(EEPROM_ADDR_PID_MAGIC, EEPROM_PID_MAGIC); int base = (id==0)?EEPROM_ADDR_PID_KP_0:EEPROM_ADDR_PID_KP_1; EEPROM.put(base, _pid[id].kp); EEPROM.put(base+4, _pid[id].ki); EEPROM.put(base+8, _pid[id].kd); }
  // Load PID gains from EEPROM (returns true if values present)
  bool loadPidFromEeprom(uint8_t id){ if (id>1) return false; if (EEPROM.read(EEPROM_ADDR_PID_MAGIC) != EEPROM_PID_MAGIC) return false; int base = (id==0)?EEPROM_ADDR_PID_KP_0:EEPROM_ADDR_PID_KP_1; float kp,ki,kd; EEPROM.get(base, kp); EEPROM.get(base+4, ki); EEPROM.get(base+8, kd); // sanity clamp
    if (!isfinite(kp) || !isfinite(ki) || !isfinite(kd)) return false; _pid[id].kp=kp; _pid[id].ki=ki; _pid[id].kd=kd; return true; }

  // Reset only the integral and derivative memory for a PID (non-invasive)
  void resetPidIntegrator(uint8_t id){ if (id>1) return; _pid[id].integral = 0.0f; _pid[id].lastError = 0.0f; _pid[id].lastMs = millis(); _pid[id].lastCount = (_hall[id])? _hall[id]->getCount() : 0; }
};

#endif // ROBOT_STEPPER_PAIR_H