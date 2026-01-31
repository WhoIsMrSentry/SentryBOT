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
#include "peripherals/xIrKeyReader.h"
// NeoPixel peripheral removed — feature disabled and code deleted

#endif // ROBOT_PERIPHERALS_H