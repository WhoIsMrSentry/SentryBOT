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

class ServoBus {
public:
  void attachAll(const uint8_t pins[SERVO_COUNT_TOTAL], const uint8_t initDeg[SERVO_COUNT_TOTAL]){
    for (int i=0;i<SERVO_COUNT_TOTAL;i++){ pinMap[i]=pins[i]; targets[i]=initDeg[i]; currents[i]=initDeg[i]; }
    beginDriver();
    // write initial pose immediately
    for (int i=0;i<SERVO_COUNT_TOTAL;i++) rawWrite(i, (int)initDeg[i]);
    lastUpdate=millis();
  }

  void setSpeed(float degPerSec){ speed=degPerSec; }

  void write(int index, float deg){ if (index<0||index>=SERVO_COUNT_TOTAL) return; targets[index]=constrain(deg,0,180); }

  void writePose(const uint8_t pose[SERVO_COUNT_TOTAL]){ for(int i=0;i<SERVO_COUNT_TOTAL;i++) targets[i]=pose[i]; }

  void update(){
    unsigned long now=millis();
    float dt = (now - lastUpdate) / 1000.0f;
    if (dt<=0) return; lastUpdate=now;
    float step = speed * dt; // deg to move this frame
    for (int i=0;i<SERVO_COUNT_TOTAL;i++){
      float cur = currents[i];
      float tgt = targets[i];
      float diff = tgt - cur;
      if (fabs(diff) < 0.5f) { currents[i]=tgt; rawWrite(i, (int)tgt); continue; }
      float delta = constrain(diff, -step, step);
      cur += delta; currents[i]=cur; rawWrite(i, (int)cur);
    }
  }

  float get(int index) const { return currents[index]; }
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
#if SERVO_USE_PCA9685
    if (!driverOk()) return;
    // Full off for all channels to release torque
    for (int i=0;i<SERVO_COUNT_TOTAL;i++){ channelFullOff(pinMap[i]); }
#else
    for(int i=0;i<SERVO_COUNT_TOTAL;i++){ if(servos[i].attached()) servos[i].detach(); }
#endif
  }
  void reattachAll(){
#if SERVO_USE_PCA9685
    // Ensure driver initialized
    if (!driverReady) beginDriver();
    if (!driverOk()) return;
    for (int i=0;i<SERVO_COUNT_TOTAL;i++) rawWrite(i, (int)currents[i]);
#else
    for(int i=0;i<SERVO_COUNT_TOTAL;i++){ if(!servos[i].attached()) servos[i].attach(pinMap[i]); servos[i].write((int)currents[i]); }
#endif
  }

  void detachOne(int index){
    if(index<0||index>=SERVO_COUNT_TOTAL) return;
#if SERVO_USE_PCA9685
    if (!driverOk()) return;
    channelFullOff(pinMap[index]);
#else
    if(servos[index].attached()) servos[index].detach();
#endif
  }
  void reattachOne(int index){
    if(index<0||index>=SERVO_COUNT_TOTAL) return;
#if SERVO_USE_PCA9685
    if (!driverOk()) return;
    // Write current angle back to re-enable PWM
    rawWrite(index, (int)currents[index]);
#else
    if(!servos[index].attached()){ servos[index].attach(pinMap[index]); servos[index].write((int)currents[index]); }
#endif
  }

  bool isSettled(float eps=0.7f) const {
    for (int i=0;i<SERVO_COUNT_TOTAL;i++){
      if (fabs(targets[i]-currents[i])>eps) return false;
    }
    return true;
  }

private:
#if SERVO_USE_PCA9685
  // Minimal PCA9685 driver (no external lib) for 50Hz servo pulses
  // Registers
  static constexpr uint8_t MODE1 = 0x00;
  static constexpr uint8_t PRESCALE = 0xFE;
  static constexpr uint8_t LED0_ON_L = 0x06;
  bool i2cPing() const {
    Wire.beginTransmission(PCA9685_ADDR);
    return (Wire.endTransmission() == 0);
  }
  void i2cWrite8(uint8_t reg, uint8_t val){ Wire.beginTransmission(PCA9685_ADDR); Wire.write(reg); Wire.write(val); Wire.endTransmission(); }
  uint8_t i2cRead8(uint8_t reg){ Wire.beginTransmission(PCA9685_ADDR); Wire.write(reg); Wire.endTransmission(); Wire.requestFrom((int)PCA9685_ADDR, 1); return Wire.available()?Wire.read():0; }
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
    Wire.endTransmission();
  }
  void channelFullOff(uint8_t ch){
    uint8_t reg = LED0_ON_L + 4*ch;
    Wire.beginTransmission(PCA9685_ADDR);
    Wire.write(reg);
    // ON=0, OFF full-off bit set
    Wire.write(0x00); Wire.write(0x00);
    Wire.write(0x00); Wire.write(0x10);
    Wire.endTransmission();
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
    // Avoid hard lock if a device disappears or bus glitches.
    Wire.setWireTimeout(25000, true);
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
  float speed = SPEED_DEG_PER_S; // deg/s
  unsigned long lastUpdate=0;
  uint8_t pinMap[SERVO_COUNT_TOTAL] = {0};
};

#endif // ROBOT_SERVO_BUS_H