#include <WiFi.h>
#include <ESPmDNS.h>
#include <WebServer.h>
#include <ArduinoJson.h>

#include "config.h"
#include "index.h"
#include "RobotState.h"
#include "UartHandler.h"

HardwareSerial MegaUart(2);
RobotState g_robotState;
WebServer server(HTTP_PORT);

// WiFi status tracking
volatile bool g_wifiConnected = false;
volatile bool g_linkAlive = false;

// Response buffer: Mega'dan gelen cevapları tutuyor
StaticJsonDocument<JSON_DOC_SIZE> g_responseBuffer;
volatile bool g_responseReady = false;

// Forward declarations
void setupWiFi();
void setupWebServer();
void handleSend();
void handleRequest();
void handleHealthz();
void handleRoot();

void setup() {
    Serial.begin(115200);
    Serial.println("\n\nSentryBOT ESP Bridge Starting (RTOS Mode)...");

    // Setup WiFi and mDNS
    setupWiFi();
    setupWebServer();

    // Initialize UART and tasks (UART2 init happens here)
    initUartTask();
    initLinkTask();

    Serial.println("Bridge Tasks Initialized.");
}

void loop() {
    // Handle HTTP requests
    if (g_wifiConnected && WiFi.status() == WL_CONNECTED) {
        server.handleClient();
    }
    vTaskDelay(pdMS_TO_TICKS(10));
}

void setupWiFi() {
    Serial.print("Connecting to WiFi: ");
    Serial.println(WIFI_SSID);
    
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    
    int retry = 0;
    const int MAX_RETRY = 20; // 10 seconds
    
    while (WiFi.status() != WL_CONNECTED && retry < MAX_RETRY) {
        delay(500);
        Serial.print(".");
        retry++;
    }
    
    if (WiFi.status() == WL_CONNECTED) {
        g_wifiConnected = true;
        Serial.println();
        Serial.print("WiFi Connected! IP: ");
        Serial.println(WiFi.localIP());
        
        // Setup mDNS
        if (!MDNS.begin(MDNS_HOSTNAME)) {
            Serial.println("MDNS initialization failed");
        } else {
            Serial.print("mDNS initialized as: ");
            Serial.print(MDNS_HOSTNAME);
            Serial.println(".local");
            MDNS.addService("http", "tcp", HTTP_PORT);
        }
    } else {
        g_wifiConnected = false;
        Serial.println();
        Serial.println("WiFi connection failed. Bridge will operate in UART-only mode.");
    }
}

void setupWebServer() {
    server.on("/", HTTP_GET, handleRoot);
    server.on("/send", HTTP_POST, handleSend);
    server.on("/request", HTTP_POST, handleRequest);
    server.on("/healthz", HTTP_GET, handleHealthz);
    
    server.begin();
    Serial.print("HTTP server started on port ");
    Serial.println(HTTP_PORT);
}

void handleSend() {
    // /send: fire-and-forget JSON to Mega
    if (!server.hasArg("plain")) {
        server.send(400, "application/json", "{\"ok\":false,\"error\":\"no payload\"}");
        return;
    }
    
    String payload = server.arg("plain");
    MegaUart.println(payload);
    
    server.send(200, "application/json", "{\"ok\":true}");
}

void handleRequest() {
    // /request: send JSON to Mega and wait for response
    if (!server.hasArg("plain")) {
        server.send(400, "application/json", "{\"ok\":false,\"error\":\"no payload\"}");
        return;
    }
    
    String payload = server.arg("plain");
    g_responseReady = false;  // Clear previous response
    MegaUart.println(payload);
    
    // Wait for response with timeout (500ms)
    unsigned long startTime = millis();
    const unsigned long RESPONSE_TIMEOUT = 500;
    
    while (!g_responseReady && (millis() - startTime) < RESPONSE_TIMEOUT) {
        delay(5);  // Small delay to allow other tasks
    }
    
    if (g_responseReady) {
        // Send response back to RPi
        String response;
        serializeJson(g_responseBuffer, response);
        server.send(200, "application/json", response);
        g_responseReady = false;
    } else {
        // Timeout: Mega didn't respond in time
        server.send(504, "application/json", "{\"ok\":false,\"error\":\"timeout_waiting_for_mega_response\"}");
    }
}

void handleHealthz() {
    // /healthz: basic status check
    bool uartOk = (MegaUart.available() >= 0); // simple check
    bool linkOk = g_linkAlive;
    
    StaticJsonDocument<256> doc;
    doc["ok"] = uartOk && g_wifiConnected;
    doc["wifi"] = g_wifiConnected;
    doc["link"] = linkOk;
    doc["rssi"] = WiFi.RSSI();
    
    String response;
    serializeJson(doc, response);
    server.send(200, "application/json", response);
}

void handleRoot() {
    server.send(200, "text/html", INDEX_HTML);
}
