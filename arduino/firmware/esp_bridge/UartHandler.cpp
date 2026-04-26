#include "UartHandler.h"

extern HardwareSerial MegaUart;

void uartTask(void* pvParameters) {
    String buffer = "";
    buffer.reserve(SERIAL_BUF_SIZE);

    while (true) {
        while (MegaUart.available()) {
            char c = (char)MegaUart.read();
            if (c == '\r') continue;
            if (c == '\n') {
                if (buffer.length() > 0) {
                    g_robotState.updateFromJson(buffer);
                    Serial.print("Mega: ");
                    Serial.println(buffer);
                    buffer = "";
                }
            } else {
                buffer += c;
                if (buffer.length() > SERIAL_BUF_SIZE) buffer = "";
            }
        }
        vTaskDelay(pdMS_TO_TICKS(5)); // Yield to other tasks
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
