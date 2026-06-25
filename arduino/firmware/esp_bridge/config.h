#ifndef BRIDGE_CONFIG_H
#define BRIDGE_CONFIG_H

#include <Arduino.h>

// WiFi Credentials — override via platformio.ini build_flags or env vars
//   build_flags = -DWIFI_SSID='"MySSID"' -DWIFI_PASS='"MyPass"'
// Do NOT commit real credentials; use a config/local_config.h pattern.
#ifndef WIFI_SSID
#define WIFI_SSID "SentryBOT"
#endif
#ifndef WIFI_PASS
#define WIFI_PASS "SentryBOT"
#endif

// mDNS hostname (accessible as "sentrybot.local")
#define MDNS_HOSTNAME "sentrybot"

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

// Task Priorities
#define PRIORITY_UART   5
#define PRIORITY_WEB    4
#define PRIORITY_WIFI   2

// Buffers
#define SERIAL_BUF_SIZE 1024
#define JSON_DOC_SIZE   2048

#endif
