#ifndef ROBOT_STATE_H
#define ROBOT_STATE_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include "config.h"

struct RobotData {
    float pitch = 0.0f;
    float roll = 0.0f;
    float ultra_cm = NAN;
    String last_rfid = "";
    String mode = "";
    bool estop = false;
    uint32_t i2c_errors = 0;
    float pose[4] = {90.0f, 90.0f, 90.0f, 90.0f};
    int32_t stepper_pos[2] = {0, 0};
    float temps[8] = {NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN};
    uint32_t last_update_ms = 0;
    uint32_t uart_rx_errors = 0;
    uint32_t uart_overflows = 0;
    bool link_alive = false;
};

class RobotState {
public:
    RobotState() {
        _mutex = xSemaphoreCreateMutex();
    }

    // Update cached robot snapshot from an already-validated JSON document.
    void updateFromDoc(const JsonDocument& doc) {
        if (xSemaphoreTake(_mutex, pdMS_TO_TICKS(10))) {
            if (doc.containsKey("pitch")) _data.pitch = doc["pitch"].as<float>();
            if (doc.containsKey("roll")) _data.roll = doc["roll"].as<float>();
            if (doc.containsKey("ultra_cm")) {
                _data.ultra_cm = doc["ultra_cm"].isNull() ? NAN : doc["ultra_cm"].as<float>();
            } else if (doc.containsKey("cm")) {
                _data.ultra_cm = doc["cm"].isNull() ? NAN : doc["cm"].as<float>();
            }
            if (doc.containsKey("mode") && doc["mode"].is<const char*>()) {
                _data.mode = doc["mode"].as<String>();
            }
            if (doc.containsKey("estop")) {
                _data.estop = doc["estop"].as<bool>();
            }
            if (doc.containsKey("i2c_errors")) {
                _data.i2c_errors = doc["i2c_errors"].as<uint32_t>();
            }
            if (doc.containsKey("rfid") && doc["rfid"].is<const char*>()) {
                _data.last_rfid = doc["rfid"].as<String>();
            }
            if (doc.containsKey("event")) {
                const char* evt = doc["event"].as<const char*>();
                if (evt && strcmp(evt, "rfid") == 0 && doc["uid"].is<const char*>()) {
                    _data.last_rfid = doc["uid"].as<String>();
                } else if (evt && strcmp(evt, "estop") == 0) {
                    _data.estop = true;
                }
            }
            if (doc.containsKey("pose") && doc["pose"].is<JsonArrayConst>()) {
                JsonArrayConst arr = doc["pose"].as<JsonArrayConst>();
                for (int i = 0; i < 4 && i < (int)arr.size(); i++) {
                    _data.pose[i] = arr[i].as<float>();
                }
            }
            if (doc.containsKey("stepper_pos") && doc["stepper_pos"].is<JsonArrayConst>()) {
                JsonArrayConst arr = doc["stepper_pos"].as<JsonArrayConst>();
                for (int i = 0; i < 2 && i < (int)arr.size(); i++) {
                    _data.stepper_pos[i] = arr[i].as<int32_t>();
                }
            }
            if (doc.containsKey("temps") && doc["temps"].is<JsonArrayConst>()) {
                JsonArrayConst arr = doc["temps"].as<JsonArrayConst>();
                for (int i = 0; i < 8 && i < (int)arr.size(); i++) {
                    _data.temps[i] = arr[i].isNull() ? NAN : arr[i].as<float>();
                }
            }
            _data.last_update_ms = millis();
            xSemaphoreGive(_mutex);
        }
    }

    void recordRxError() {
        if (xSemaphoreTake(_mutex, pdMS_TO_TICKS(10))) {
            _data.uart_rx_errors++;
            xSemaphoreGive(_mutex);
        }
    }

    void recordOverflow() {
        if (xSemaphoreTake(_mutex, pdMS_TO_TICKS(10))) {
            _data.uart_overflows++;
            xSemaphoreGive(_mutex);
        }
    }

    RobotData get() {
        RobotData copy;
        if (xSemaphoreTake(_mutex, pdMS_TO_TICKS(50))) {
            copy = _data;
            // Dynamic link_alive: true only when at least one valid frame arrived within timeout
            copy.link_alive = (_data.last_update_ms > 0) && ((millis() - _data.last_update_ms) <= LINK_TIMEOUT_MS);
            xSemaphoreGive(_mutex);
        }
        return copy;
    }

private:
    RobotData _data;
    SemaphoreHandle_t _mutex;
};

extern RobotState g_robotState;

#endif
