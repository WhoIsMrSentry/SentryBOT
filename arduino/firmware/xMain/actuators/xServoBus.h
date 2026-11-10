#ifndef ROBOT_SERVO_BUS_H
#define ROBOT_SERVO_BUS_H

#include <Arduino.h>
#if SERVO_USE_PCA9685
#include <Wire.h>
#else
#include <Servo.h>
#endif
#include <math.h>
#include "../xConfig.h"
#include "../xProtocol.h"

#if defined(ARDUINO_ARCH_AVR)
#include <avr/pgmspace.h>
#endif

class ServoBus {
public:
  // Initialize all servos from a RAM array.
  void attachAll(const uint8_t pins[SERVO_COUNT_TOTAL], const uint8_t initDeg[SERVO_COUNT_TOTAL]){
    attachAllImpl(pins, initDeg, false);
  }

  // Initialize all servos from a PROGMEM array on AVR.
  void attachAllProgmem(const uint8_t pins[SERVO_COUNT_TOTAL], const uint8_t initDegProgmem[SERVO_COUNT_TOTAL]){
    attachAllImpl(pins, initDegProgmem, true);
  }

  void setSpeed(float degPerSec){
    if (degPerSec > 0.0f) {
      speed = degPerSec;
      _hasSavedSpeed = false;
    }
  }

  // Temporarily override easing speed for a timed pose, restoring prior speed once settled.
  void setTemporarySpeed(float degPerSec){
    if (degPerSec <= 0.0f) return;
    if (!_hasSavedSpeed) _savedSpeed = speed;
    _hasSavedSpeed = true;
    speed = degPerSec;
  }

  float getSpeed() const { return speed; }

  void write(int index, float deg){
    if (index<0||index>=SERVO_COUNT_TOTAL) return;
    targets[index]=constrain(deg,0,180);
  }

  void writePose(const uint8_t pose[SERVO_COUNT_TOTAL]){
    for(int i=0;i<SERVO_COUNT_TOTAL;i++) targets[i]=constrain((float)pose[i], 0.0f, 180.0f);
  }

  void writePoseProgmem(const uint8_t pose[SERVO_COUNT_TOTAL]){
    for(int i=0;i<SERVO_COUNT_TOTAL;i++) targets[i]=constrain((float)readPoseByteProgmem(pose, i), 0.0f, 180.0f);
  }

  void update(){
    unsigned long now=millis();
    if (_estopped) {
      lastUpdate = now;
      return;
    }
    float dt = (now - lastUpdate) / 1000.0f;
    if (dt<=0) return;
    lastUpdate=now;
    float step = speed * dt; // deg to move this frame
    bool allSettled = true;
    for (int i=0;i<SERVO_COUNT_TOTAL;i++){
      float cur = currents[i];
      float tgt = targets[i];
      float diff = tgt - cur;
      if (fabs(diff) < 0.5f) {
        currents[i]=tgt;
      } else {
        allSettled = false;
        float delta = constrain(diff, -step, step);
        cur += delta;
        currents[i]=cur;
      }
      int outDeg = (int)currents[i];
      if (outDeg != _lastWritten[i]) {
        rawWrite(i, outDeg);
        _lastWritten[i] = outDeg;
      }
    }
    if (allSettled && _hasSavedSpeed) {
      speed = _savedSpeed;
      _hasSavedSpeed = false;
    }
  }

  float get(int index) const { return (index>=0 && index<SERVO_COUNT_TOTAL) ? currents[index] : 0.0f; }
  float getTarget(int index) const { return (index>=0 && index<SERVO_COUNT_TOTAL) ? targets[index] : 0.0f; }
  bool isEstopped() const { return _estopped; }
  bool attached(int index) const {
    if(index<0||index>=SERVO_COUNT_TOTAL) return false;
#if SERVO_USE_PCA9685
    // PCA9685 doesn't have 'attached' per channel; assume attached after begin
    return driverReady && driverPresent;
#else
    return servos[index].attached();
#endif
  }

  bool driverOk() const {
#if SERVO_USE_PCA9685
    return driverReady && driverPresent;
#else
    return true;
#endif
  }

  void detachAll(){
    _estopped = true;
    for (int i=0;i<SERVO_COUNT_TOTAL;i++) _lastWritten[i] = -1;
#if SERVO_USE_PCA9685
    if (!driverOk()) return;
    // Full off for all channels to release torque
    for (int i=0;i<SERVO_COUNT_TOTAL;i++){ channelFullOff(pinMap[i]); }
#else
    for(int i=0;i<SERVO_COUNT_TOTAL;i++){ if(servos[i].attached()) servos[i].detach(); }
#endif
  }
  void reattachAll(){
    _estopped = false;
    for (int i=0;i<SERVO_COUNT_TOTAL;i++) _lastWritten[i] = -1;
#if SERVO_USE_PCA9685
    // Ensure driver initialized
    if (!driverReady) beginDriver();
    if (!driverOk()) return;
    for (int i=0;i<SERVO_COUNT_TOTAL;i++){
      int d = (int)currents[i];
      rawWrite(i, d);
      _lastWritten[i] = d;
    }
#else
    for(int i=0;i<SERVO_COUNT_TOTAL;i++){
      if(!servos[i].attached()) servos[i].attach(pinMap[i]);
      int d = (int)currents[i];
      servos[i].write(d);
      _lastWritten[i] = d;
    }
#endif
  }

  void detachOne(int index){
    if(index<0||index>=SERVO_COUNT_TOTAL) return;
    _lastWritten[index] = -1;
#if SERVO_USE_PCA9685
    if (!driverOk()) return;
    channelFullOff(pinMap[index]);
#else
    if(servos[index].attached()) servos[index].detach();
#endif
  }
  void reattachOne(int index){
    if(index<0||index>=SERVO_COUNT_TOTAL || _estopped) return;
#if SERVO_USE_PCA9685
    if (!driverOk()) return;
    // Write current angle back to re-enable PWM
    int d = (int)currents[index];
    rawWrite(index, d);
    _lastWritten[index] = d;
#else
    if(!servos[index].attached()){
      servos[index].attach(pinMap[index]);
    }
    int d = (int)currents[index];
    servos[index].write(d);
    _lastWritten[index] = d;
#endif
  }

  bool isSettled(float eps=0.7f) const {
    for (int i=0;i<SERVO_COUNT_TOTAL;i++){
      if (fabs(targets[i]-currents[i])>eps) return false;
    }
    return true;
  }

private:
  void attachAllImpl(const uint8_t pins[SERVO_COUNT_TOTAL], const uint8_t *initDeg, bool progmem){
    _estopped = false;
    for (int i=0;i<SERVO_COUNT_TOTAL;i++){
      pinMap[i] = pins[i];
      targets[i] = progmem ? readPoseByteProgmem(initDeg, i) : initDeg[i];
      currents[i] = targets[i];
      _lastWritten[i] = -1;
    }
    beginDriver();
    // write initial pose immediately
    for (int i=0;i<SERVO_COUNT_TOTAL;i++){
      int d = (int)targets[i];
      rawWrite(i, d);
      _lastWritten[i] = d;
    }
    lastUpdate=millis();
  }

  static uint8_t readPoseByteProgmem(const uint8_t *pose, int index){
#if defined(ARDUINO_ARCH_AVR)
    return pgm_read_byte(&pose[index]);
#else
    return pose[index];
#endif
  }

#if SERVO_USE_PCA9685
  // Minimal PCA9685 driver (no external lib) for 50Hz servo pulses
  // Registers
  static constexpr uint8_t MODE1 = 0x00;
  static constexpr uint8_t PRESCALE = 0xFE;
  static constexpr uint8_t LED0_ON_L = 0x06;
  bool i2cPing() const {
    Wire.beginTransmission(PCA9685_ADDR);
    uint8_t st = Wire.endTransmission();
    Protocol::pollWireTimeout();
    return (st == 0);
  }
  void i2cWrite8(uint8_t reg, uint8_t val){
    Wire.beginTransmission(PCA9685_ADDR);
    Wire.write(reg);
    Wire.write(val);
    Protocol::recordWireStatus(Wire.endTransmission());
  }
  uint8_t i2cRead8(uint8_t reg){
    Wire.beginTransmission(PCA9685_ADDR);
    Wire.write(reg);
    Protocol::recordWireStatus(Wire.endTransmission());
    Wire.requestFrom((int)PCA9685_ADDR, 1);
    Protocol::pollWireTimeout();
    return Wire.available()?Wire.read():0;
  }
  void setPwmFreq(float hz){
    // prescale = round(25MHz / (4096*hz)) - 1
    float prescaleval = 25000000.0f; prescaleval /= 4096.0f; prescaleval /= hz; prescaleval -= 1.0f;
    uint8_t prescale = (uint8_t)floor(prescaleval + 0.5f);
    uint8_t oldmode = i2cRead8(MODE1);
    uint8_t sleep = (oldmode & 0x7F) | 0x10; // sleep
    i2cWrite8(MODE1, sleep);
    i2cWrite8(PRESCALE, prescale);
    i2cWrite8(MODE1, oldmode);
    delay(5);
    i2cWrite8(MODE1, oldmode | 0xA1); // auto-increment + allcall
  }
  void setPwm(uint8_t ch, uint16_t on, uint16_t off){
    uint8_t reg = LED0_ON_L + 4*ch;
    Wire.beginTransmission(PCA9685_ADDR);
    Wire.write(reg);
    Wire.write(on & 0xFF); Wire.write(on >> 8);
    Wire.write(off & 0xFF); Wire.write(off >> 8);
    Protocol::recordWireStatus(Wire.endTransmission());
  }
  void channelFullOff(uint8_t ch){
    uint8_t reg = LED0_ON_L + 4*ch;
    Wire.beginTransmission(PCA9685_ADDR);
    Wire.write(reg);
    // ON=0, OFF full-off bit set
    Wire.write(0x00); Wire.write(0x00);
    Wire.write(0x00); Wire.write(0x10);
    Protocol::recordWireStatus(Wire.endTransmission());
  }
  uint16_t usToTicks(int us){
    // For 50Hz: period = 20000us, ticks = us/20000 * 4096 = us * 0.2048
    // To avoid float at runtime, do scaled integer math
    long ticks = (long)us * 4096L / 20000L; if (ticks<0) ticks=0; if (ticks>4095) ticks=4095; return (uint16_t)ticks;
  }
  void angleWrite(uint8_t ch, int deg){
    deg = constrain(deg, 0, 180);
    int us = SERVO_MIN_US + (int)((long)(SERVO_MAX_US - SERVO_MIN_US) * deg / 180L);
    uint16_t off = usToTicks(us);
    setPwm(ch, 0, off);
  }
  void beginDriver(){
    if (driverReady) return;
    Wire.begin();
#if defined(ARDUINO_ARCH_AVR)
    // Avoid hard lock if a device disappears or bus glitches; auto-reset on
    // timeout so other I2C peripherals (LCD) keep working after a stuck slave.
    Wire.setWireTimeout(I2C_WIRE_TIMEOUT_US, true);
#endif
    driverPresent = i2cPing();
    if (!driverPresent){
      driverReady = true; // initialized but unavailable -> keep writes as no-op
      return;
    }
    i2cWrite8(MODE1, 0x00);
    delay(5);
    setPwmFreq(SERVO_FREQ_HZ);
    driverReady = true;
  }
  void rawWrite(int index, int deg){
    if (!driverOk()) return;
    angleWrite(pinMap[index], deg);
  }
  bool driverReady=false;
  bool driverPresent=false;
#else
  Servo servos[SERVO_COUNT_TOTAL];
  void beginDriver(){ /* no-op for direct Servo */ for (int i=0;i<SERVO_COUNT_TOTAL;i++){ servos[i].attach(pinMap[i]); servos[i].write((int)targets[i]); } }
  void rawWrite(int index, int deg){ servos[index].write((int)deg); }
#endif
  float currents[SERVO_COUNT_TOTAL] = {0};
  float targets[SERVO_COUNT_TOTAL]  = {0};
  int16_t _lastWritten[SERVO_COUNT_TOTAL] = {-1, -1, -1, -1};
  float speed = SPEED_DEG_PER_S; // deg/s
  float _savedSpeed = SPEED_DEG_PER_S;
  bool _hasSavedSpeed = false;
  bool _estopped = false;
  unsigned long lastUpdate=0;
  uint8_t pinMap[SERVO_COUNT_TOTAL] = {0};
};

#endif // ROBOT_SERVO_BUS_H