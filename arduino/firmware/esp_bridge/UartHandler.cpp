#include "UartHandler.h"
#include <ctype.h>
#include <ArduinoJson.h>

extern HardwareSerial MegaUart;
extern volatile bool g_linkAlive;
extern StaticJsonDocument<2048> g_responseBuffer;  // Response buffer
extern volatile bool g_responseReady;               // Response ready flag

// Robust line buffer with validation
static char lineBuffer[SERIAL_BUF_SIZE];
static int lineIdx = 0;

static inline bool isValidJsonStart(char c) {
    return c == '{' || isspace(c);
}

static inline bool isValidJsonChar(char c) {
    return (c >= 32 && c < 127) || c == '\n' || c == '\r';
}

void uartTask(void* pvParameters) {
    (void)pvParameters;
    unsigned long lastValidMs = millis();
    const unsigned long RESET_TIMEOUT = 2000; // Reset buffer after 2s silence

    while (true) {
        if (!MegaUart.available()) {
            vTaskDelay(pdMS_TO_TICKS(2));
            // Check for stale incomplete buffer
            if (lineIdx > 0 && (millis() - lastValidMs) > RESET_TIMEOUT) {
                lineIdx = 0;
            }
            continue;
        }

        char c = (char)MegaUart.read();
        
        // Validate character
        if (!isValidJsonChar(c)) {
            // Invalid char: skip and reset if buffer is empty
            if (lineIdx == 0) continue;
            // Otherwise drop this char but keep buffer
            continue;
        }

        // Skip leading whitespace
        if (lineIdx == 0 && isspace(c)) continue;

        // Handle line ending
        if (c == '\n' || c == '\r') {
            if (lineIdx > 0) {
                lineBuffer[lineIdx] = '\0';
                // Validate and parse
                if (lineBuffer[0] == '{' && lineIdx > 2) {
                    g_robotState.updateFromJson(String(lineBuffer));
                    
                    // TWO-WAY ROUTING: Parse JSON and store in response buffer
                    DeserializationError error = deserializeJson(g_responseBuffer, lineBuffer);
                    if (!error) {
                        g_responseReady = true;  // Signal response ready for HTTP handler
                    }
                    
                    Serial.print("Mega: ");
                    Serial.println(lineBuffer);
                    lastValidMs = millis();
                }
                lineIdx = 0;
            }
            continue;
        }

        // Buffer management: prevent overflow
        if (lineIdx >= SERIAL_BUF_SIZE - 2) {
            // Buffer full without closing: reset and skip
            lineIdx = 0;
            Serial.println("[UART] Buffer overflow, reset");
            continue;
        }

        // Add character to buffer
        lineBuffer[lineIdx++] = c;
        lastValidMs = millis();
    }
}

void linkTask(void* pvParameters) {
    (void)pvParameters;
    vTaskDelay(pdMS_TO_TICKS(500)); // Wait for Mega to be ready
    
    // Send initial telemetry start command
    MegaUart.println(F("{\"cmd\":\"telemetry_start\"}"));
    g_linkAlive = true;  // Mark link as established
    
    unsigned long lastHbMs = millis();
    
    while (true) {
        unsigned long nowMs = millis();
        
        // Send heartbeat every HB_INTERVAL_MS (200ms)
        if (nowMs - lastHbMs >= HB_INTERVAL_MS) {
            MegaUart.println(F("{\"cmd\":\"hb\"}"));
            lastHbMs = nowMs;
        }
        
        vTaskDelay(pdMS_TO_TICKS(50)); // Small delay to avoid hogging CPU
    }
}

void initUartTask() {
    MegaUart.begin(UART_BAUD, SERIAL_8N1, UART_RX_PIN, UART_TX_PIN);
    xTaskCreate(
        uartTask,
        "UartTask",
        4096,
        NULL,
        PRIORITY_UART,
        NULL
    );
}

void initLinkTask() {
    xTaskCreate(
        linkTask,
        "LinkTask",
        2048,
        NULL,
        PRIORITY_UART + 1, // Slightly higher priority than UART
        NULL
    );
}
