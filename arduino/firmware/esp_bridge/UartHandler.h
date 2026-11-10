#ifndef UART_HANDLER_H
#define UART_HANDLER_H

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include "config.h"
#include "RobotState.h"

void initUartTask();
void initLinkTask();

// Thread-safe UART TX helper (serialized by FreeRTOS mutex)
bool uartSendLine(const char* line);
bool uartSendLine(const String& line);

// FreeRTOS queue-backed response capture for /request handlers
void uartBeginResponseWindow();
void uartEndResponseWindow();
bool uartReceiveResponseLine(char* outBuf, size_t maxLen, TickType_t waitTicks);

#endif
