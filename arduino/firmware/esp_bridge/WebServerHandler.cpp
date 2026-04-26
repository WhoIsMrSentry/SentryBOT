#include "WebServerHandler.h"
#include <WiFi.h>
#include <ESPmDNS.h>

extern WebServer server;
extern HardwareSerial MegaUart;

void handleIndex() {
    server.send_P(200, "text/html", INDEX_HTML);
}

void handleApiState() {
    RobotData data = g_robotState.get();
    DynamicJsonDocument doc(2048);
    doc["link_alive"] = data.link_alive;
    doc["pitch"] = data.pitch;
    doc["roll"] = data.roll;
    doc["ultra_cm"] = data.ultra_cm;
    doc["last_rfid"] = data.last_rfid;
    
    JsonArray tArr = doc.createNestedArray("temps");
    for(int i=0; i<8; i++) tArr.add(data.temps[i]);
    
    doc["ts"] = data.last_update_ms;

    String body;
    serializeJson(doc, body);
    server.send(200, "application/json", body);
}

void handleSend() {
    if (!server.hasArg("plain")) {
        server.send(400, "application/json", "{\"ok\":false}");
        return;
    }
    MegaUart.print(server.arg("plain"));
    MegaUart.print('\n');
    server.send(200, "application/json", "{\"ok\":true}");
}

void handleRaw() {
    if (!server.hasArg("plain")) {
        server.send(400, "application/json", "{\"ok\":false}");
        return;
    }
    String key = server.arg("plain");
    MegaUart.print(key);
    MegaUart.print('\n');
    server.send(200, "application/json", "{\"ok\":true}");
}

void webServerTask(void* pvParameters) {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    
    while (WiFi.status() != WL_CONNECTED) {
        vTaskDelay(pdMS_TO_TICKS(500));
    }

    if (MDNS.begin(HOSTNAME)) {
        MDNS.addService("http", "tcp", 80);
    }

    server.on("/", HTTP_GET, handleIndex);
    server.on("/api/state", HTTP_GET, handleApiState);
    server.on("/send", HTTP_POST, handleSend);
    server.on("/raw", HTTP_POST, handleRaw);
    server.on("/healthz", HTTP_GET, []() { server.send(200, "text/plain", "OK"); });
    
    server.begin();

    while (true) {
        server.handleClient();
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

void initWebServerTask() {
    xTaskCreate(
        webServerTask,
        "WebServerTask",
        8192,
        NULL,
        PRIORITY_SERVER,
        NULL
    );
}
