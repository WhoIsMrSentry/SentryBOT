#include "actuators/xNemaController.h"
#include "xConfig.h"
#include "xRobot.h"

extern Robot robot;
extern EbyteRadio g_ebyteRadio;

NemaController g_nema(&robot.steppers, &g_ebyteRadio);

NemaController::NemaController(StepperPair* pair, EbyteRadio* radio): steppers(pair), radio(radio) {}

void NemaController::begin(){
  // StepperPair is already initialized by Robot::begin().
}

void NemaController::applyJoystick(int8_t x, int8_t y){
  if (!_enabled){
    if (steppers) steppers->setSpeed(0.0f, 0.0f);
    return;
  }
  float nx = (float)x / 127.0f;
  float ny = (float)y / 127.0f;
  float left = ny + nx;
  float right = ny - nx;
  left = constrain(left, -1.0f, 1.0f);
  right = constrain(right, -1.0f, 1.0f);
  float lspd = left * maxSpeedStepsPerSec;
  float rspd = right * maxSpeedStepsPerSec;
  if (!leftEnabled) lspd = 0.0f;
  if (!rightEnabled) rspd = 0.0f;
  steppers->setSpeed(lspd, rspd);
}

void NemaController::update(){
  if (radio && radio->newPacket){
    MasterPacket1 pkt = radio->lastPkt;
    radio->newPacket = false;
    const uint16_t BTN_MOTOR1 = (1<<9);
    const uint16_t BTN_MOTOR2 = (1<<10);
    rightEnabled = (pkt.Buttons & BTN_MOTOR1);
    leftEnabled  = (pkt.Buttons & BTN_MOTOR2);
    applyJoystick(pkt.Rstick_X, pkt.Rstick_Y);
    String s = String("SRC:") + radio->lastSource + " ";
    s += String("X=") + pkt.Rstick_X + ",Y=" + pkt.Rstick_Y;
    SERIAL_IO.println(s);
  }
  if (steppers) steppers->update();
}

void NemaController::setEnabled(bool en){
  _enabled = en;
  if (!_enabled && steppers){
    steppers->setSpeed(0.0f, 0.0f);
  }
  if (steppers){
    steppers->setEnable(en);
  }
}


bool NemaController::isEnabled() const { return _enabled; }
bool NemaController::isLeftMotorEnabled() const { return leftEnabled; }
bool NemaController::isRightMotorEnabled() const { return rightEnabled; }