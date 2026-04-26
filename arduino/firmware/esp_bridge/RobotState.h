#ifndef ROBOT_STATE_H
#define ROBOT_STATE_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

struct RobotData {
    float pitch = 0;
    float roll = 0;
    float ultra_cm = 0;
    String last_rfid = "";
    String last_speech = "";
    float temps[8] = {NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN};
    uint32_t last_update_ms = 0;
    bool link_alive = false;
};

class RobotState {
public:
    RobotState() {
        _mutex = xSemaphoreCreateMutex();
    }

    void updateFromJson(const String& json) {
        DynamicJsonDocument doc(2048);
        DeserializationError err = deserializeJson(doc, json);
        if (err) return;

        if (xSemaphoreTake(_mutex, pdMS_TO_TICKS(10))) {
            if (doc.containsKey("pitch")) _data.pitch = doc["pitch"];
            if (doc.containsKey("roll")) _data.roll = doc["roll"];
            if (doc.containsKey("ultra_cm")) _data.ultra_cm = doc["ultra_cm"];
            if (doc.containsKey("rfid")) _data.last_rfid = doc["rfid"].as<String>();
            if (doc.containsKey("event")) {
                if (doc["event"] == "rfid") _data.last_rfid = doc["uid"].as<String>();
            }
            if (doc.containsKey("temps")) {
                JsonArray arr = doc["temps"];
                for(int i=0; i<8 && i<arr.size(); i++) _data.temps[i] = arr[i];
            }
            _data.last_update_ms = millis();
            _data.link_alive = true;
            xSemaphoreGive(_mutex);
        }
    }

    RobotData get() {
        RobotData copy;
        if (xSemaphoreTake(_mutex, pdMS_TO_TICKS(50))) {
            copy = _data;
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
