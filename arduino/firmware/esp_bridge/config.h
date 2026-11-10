#ifndef BRIDGE_CONFIG_H
#define BRIDGE_CONFIG_H

#include <Arduino.h>

// Optional untracked local configuration (WIFI_SSID, WIFI_PASS, BRIDGE_AUTH_TOKEN)
#if defined(__has_include)
#if __has_include("local_config.h")
#include "local_config.h"
#endif
#endif

// WiFi Credentials — set in local_config.h or build_flags:
//   -DWIFI_SSID='"MySSID"' -DWIFI_PASS='"MyPass"'
#ifndef WIFI_SSID
#define WIFI_SSID ""
#endif
#ifndef WIFI_PASS
#define WIFI_PASS ""
#endif

// Optional shared API token protecting POST /send and POST /request (empty disables token check)
#ifndef BRIDGE_AUTH_TOKEN
#define BRIDGE_AUTH_TOKEN ""
#endif

// mDNS hostname (accessible as "sentrybot-2.local", matching Pi config.yml)
#define MDNS_HOSTNAME "sentrybot-2"

// HTTP server port
#define HTTP_PORT 8080

// UART (ESP32 UART2 -> Mega UART1)
#define UART_RX_PIN 16
#define UART_TX_PIN 17
#define UART_BAUD   115200

// Link/telemetry keepalive (aggressive for stability)
#define HB_INTERVAL_MS         200
#define TELEMETRY_INTERVAL_MS  200
#define LINK_TIMEOUT_MS        1000

// Task Priorities & Queue Sizing
#define PRIORITY_UART   5
#define RX_QUEUE_DEPTH  12

// Buffers
#define SERIAL_BUF_SIZE 1024
#define JSON_DOC_SIZE   2048

#endif
