#ifndef ROBOT_PERIPHERALS_H
#define ROBOT_PERIPHERALS_H

#include <Arduino.h>
#include "xConfig.h"

// Peripheral wrappers split into small headers.
#include "peripherals/xUltrasonic.h"
#include "peripherals/xRfidReader.h"
#include "peripherals/xLcdDisplay.h"
#include "peripherals/xLaserPair.h"
#include "peripherals/xBuzzer.h"
#include "peripherals/xHallEncoder.h"
#include "peripherals/xOledDisplay.h"
#if OLED_ENABLED
extern class OledDisplay g_oled;
#endif
#include "peripherals/xIrKeyReader.h"
#include "peripherals/xEbyteRadio.h"

// Ebyte radio instance (nRF24L01 compatible)
extern EbyteRadio g_ebyteRadio;
#endif // ROBOT_PERIPHERALS_H