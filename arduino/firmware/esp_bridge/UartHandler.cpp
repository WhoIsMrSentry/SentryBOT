#include "UartHandler.h"
#include <ctype.h>
#include <string.h>
#include <ArduinoJson.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>

extern HardwareSerial MegaUart;

namespace {
struct UartRxLine {
    char text[SERIAL_BUF_SIZE];
};

SemaphoreHandle_t s_uartTxMutex = nullptr;
QueueHandle_t s_responseQueue = nullptr;
volatile bool s_waitingResponse = false;

char lineBuffer[SERIAL_BUF_SIZE];
int lineIdx = 0;

inline bool isValidJsonChar(char c) {
    return (c >= 32 && c < 127) || c == '\n' || c == '\r';
}
} // namespace

bool uartSendLine(const char* line) {
    if (!line || !s_uartTxMutex) return false;
    if (xSemaphoreTake(s_uartTxMutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        return false;
    }
    MegaUart.println(line);
    xSemaphoreGive(s_uartTxMutex);
    return true;
}

bool uartSendLine(const String& line) {
    return uartSendLine(line.c_str());
}

void uartBeginResponseWindow() {
    if (s_responseQueue) {
        xQueueReset(s_responseQueue);
    }
    s_waitingResponse = true;
}

void uartEndResponseWindow() {
    s_waitingResponse = false;
    if (s_responseQueue) {
        xQueueReset(s_responseQueue);
    }
}

bool uartReceiveResponseLine(char* outBuf, size_t maxLen, TickType_t waitTicks) {
    if (!s_responseQueue || !outBuf || maxLen == 0) return false;
    UartRxLine item;
    if (xQueueReceive(s_responseQueue, &item, waitTicks) != pdTRUE) {
        return false;
    }
    strlcpy(outBuf, item.text, maxLen);
    return true;
}

void uartTask(void* pvParameters) {
    (void)pvParameters;
    unsigned long lastValidMs = millis();
    const unsigned long RESET_TIMEOUT = 2000; // Reset buffer after 2s silence
    StaticJsonDocument<JSON_DOC_SIZE> rxDoc;

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
        if (!isValidJsonChar(c)) {
            if (lineIdx > 0) g_robotState.recordRxError();
            continue;
        }

        // Skip leading whitespace
        if (lineIdx == 0 && isspace((unsigned char)c)) continue;

        // Handle line ending
        if (c == '\n' || c == '\r') {
            if (lineIdx > 0) {
                lineBuffer[lineIdx] = '\0';
                if (lineBuffer[0] == '{' && lineIdx > 2) {
                    rxDoc.clear();
                    DeserializationError error = deserializeJson(rxDoc, lineBuffer);
                    if (!error && rxDoc.is<JsonObject>()) {
                        g_robotState.updateFromDoc(rxDoc);
                        if (s_waitingResponse && s_responseQueue) {
                            UartRxLine msg;
                            strlcpy(msg.text, lineBuffer, sizeof(msg.text));
                            xQueueSend(s_responseQueue, &msg, 0);
                        }
                        Serial.print("Mega: ");
                        Serial.println(lineBuffer);
                        lastValidMs = millis();
                    } else {
                        g_robotState.recordRxError();
                    }
                } else {
                    g_robotState.recordRxError();
                }
                lineIdx = 0;
            }
            continue;
        }

        // Buffer management: prevent overflow
        if (lineIdx >= SERIAL_BUF_SIZE - 2) {
            lineIdx = 0;
            g_robotState.recordOverflow();
            Serial.println("[UART] Buffer overflow, reset");
            continue;
        }

        lineBuffer[lineIdx++] = c;
        lastValidMs = millis();
    }
}

void linkTask(void* pvParameters) {
    (void)pvParameters;
    vTaskDelay(pdMS_TO_TICKS(500)); // Wait for Mega boot

    uartSendLine("{\"cmd\":\"telemetry_start\"}");
    unsigned long lastHbMs = millis();

    while (true) {
        unsigned long nowMs = millis();
        if (nowMs - lastHbMs >= HB_INTERVAL_MS) {
            uartSendLine("{\"cmd\":\"hb\"}");
            lastHbMs = nowMs;
        }
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}

void initUartTask() {
    if (!s_uartTxMutex) {
        s_uartTxMutex = xSemaphoreCreateMutex();
    }
    if (!s_responseQueue) {
        s_responseQueue = xQueueCreate(RX_QUEUE_DEPTH, sizeof(UartRxLine));
    }
    MegaUart.begin(UART_BAUD, SERIAL_8N1, UART_RX_PIN, UART_TX_PIN);
    xTaskCreate(
        uartTask,
        "UartTask",
        8192,
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
