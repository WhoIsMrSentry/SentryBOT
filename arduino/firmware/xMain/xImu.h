#ifndef ROBOT_IMU_H
#define ROBOT_IMU_H

#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include "xConfig.h"

class Imu {
public:
  bool begin(uint8_t addr = IMU_I2C_ADDR) {
    // Try primary address first; if module's AD0 is tied high it may be at 0x69.
    if (!mpu.begin(addr)) {
      uint8_t alt = (addr == 0x68) ? 0x69 : 0x68;
      if (!mpu.begin(alt)) return false;
    }
    mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    mpu.setGyroRange(MPU6050_RANGE_250_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
    ready = true; return true;
  }
  bool isReady() const { return ready; }

  void read() {
    if (!ready) return;
    sensors_event_t a, g, temp; mpu.getEvent(&a, &g, &temp);

    accX = a.acceleration.x;
    accY = a.acceleration.y;
    accZ = a.acceleration.z;
    gyroX = g.gyro.x;
    gyroY = g.gyro.y;
    gyroZ = g.gyro.z;
    tempC = temp.temperature;

    float accPitch = atan2(a.acceleration.x, sqrt(a.acceleration.y*a.acceleration.y + a.acceleration.z*a.acceleration.z)) * 180.0 / PI;
    float accRoll  = atan2(a.acceleration.y, sqrt(a.acceleration.x*a.acceleration.x + a.acceleration.z*a.acceleration.z)) * 180.0 / PI;
    #ifndef IMU_USE_COMPLEMENTARY
    #define IMU_USE_COMPLEMENTARY 0
    #endif
    #ifndef IMU_COMP_ALPHA
    #define IMU_COMP_ALPHA 0.98f
    #endif
    if (IMU_USE_COMPLEMENTARY){
      unsigned long now = micros();
      float dt = lastUs? (now - lastUs)/1000000.0f : 0.0f; lastUs = now;
      // Gyro rates (deg/s). Axis mapping may require tuning for your mounting.
      float gyroPitchRate = g.gyro.x; // adjust if needed
      float gyroRollRate  = g.gyro.y;
      pitch = IMU_COMP_ALPHA * (pitch + gyroPitchRate * dt) + (1.0f-IMU_COMP_ALPHA) * accPitch;
      roll  = IMU_COMP_ALPHA * (roll  + gyroRollRate  * dt) + (1.0f-IMU_COMP_ALPHA) * accRoll;
    } else {
      pitch = accPitch; roll = accRoll;
    }
  }
  float getPitch() const { return pitch - offPitch; }
  float getRoll()  const { return roll  - offRoll; }

  // Raw sensor values from the last read()
  float getAccX() const { return accX; }
  float getAccY() const { return accY; }
  float getAccZ() const { return accZ; }
  float getGyroX() const { return gyroX; }
  float getGyroY() const { return gyroY; }
  float getGyroZ() const { return gyroZ; }
  float getTempC() const { return tempC; }

  void calibrateLevel() {
    // Capture current orientation as zero-offset
    if (!ready) return;
    // Ensure fresh read
    sensors_event_t a, g, temp; mpu.getEvent(&a, &g, &temp);
    float p = atan2(a.acceleration.x, sqrt(a.acceleration.y*a.acceleration.y + a.acceleration.z*a.acceleration.z)) * 180.0 / PI;
    float r = atan2(a.acceleration.y, sqrt(a.acceleration.x*a.acceleration.x + a.acceleration.z*a.acceleration.z)) * 180.0 / PI;
    offPitch = p;
    offRoll  = r;
  }
  void setOffsets(float p, float r){ offPitch=p; offRoll=r; }
  void getOffsets(float &p, float &r) const { p=offPitch; r=offRoll; }

private:
  Adafruit_MPU6050 mpu;
  bool ready=false; 
  float pitch=0, roll=0;
  float offPitch=0, offRoll=0;
  float accX=0, accY=0, accZ=0;
  float gyroX=0, gyroY=0, gyroZ=0;
  float tempC=0;
  unsigned long lastUs=0;
};

#endif // ROBOT_IMU_H