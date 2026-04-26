#ifndef BRIDGE_CONFIG_H
#define BRIDGE_CONFIG_H

#include <Arduino.h>

// Network
#define WIFI_SSID "SentryBOT"
#define WIFI_PASS "SentryBOT"
#define HOSTNAME  "sentrybot"

// UART (ESP32 UART2 -> Mega UART1)
#define UART_RX_PIN 16
#define UART_TX_PIN 17
#define UART_BAUD   115200

// Task Priorities
#define PRIORITY_UART   5
#define PRIORITY_SERVER 4

// Buffers
#define SERIAL_BUF_SIZE 1024
#define JSON_DOC_SIZE   2048

#endif
