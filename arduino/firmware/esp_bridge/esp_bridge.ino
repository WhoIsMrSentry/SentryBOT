#include <WiFi.h>
#include <WebServer.h>
#include "config.h"
#include "RobotState.h"
#include "UartHandler.h"
#include "WebServerHandler.h"

HardwareSerial MegaUart(2);
WebServer server(80);
RobotState g_robotState;

void setup() {
    Serial.begin(115200);
    Serial.println("SentryBOT ESP Bridge Starting (RTOS Mode)...");

    // Initialize Tasks
    initUartTask();
    initWebServerTask();

    Serial.println("Bridge Tasks Initialized.");
}

void loop() {
    // Empty! RTOS tasks handle everything.
    vTaskDelay(pdMS_TO_TICKS(1000));
}
