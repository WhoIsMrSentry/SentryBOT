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
WebServer serverCompat80(80);

// WiFi status tracking
volatile bool g_wifiConnected = false;
volatile bool g_linkAlive = false;

// Response buffer: Mega'dan gelen cevapları tutuyor
StaticJsonDocument<JSON_DOC_SIZE> g_responseBuffer;
volatile bool g_responseReady = false;

// Forward declarations
void setupWiFi();
void setupWebServer();
void registerRoutes(WebServer& s);
void handleSend(WebServer& ctx);
void handleRequest(WebServer& ctx);
void handleHealthz(WebServer& ctx);
void handleRoot(WebServer& ctx);
bool responseMatchesCommand(const JsonDocument& doc, const String& cmd);

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
        if (HTTP_PORT != 80) {
            serverCompat80.handleClient();
        }
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
    registerRoutes(server);
    
    server.begin();
    Serial.print("HTTP server started on port ");
    Serial.println(HTTP_PORT);

    if (HTTP_PORT != 80) {
        registerRoutes(serverCompat80);
        serverCompat80.begin();
        Serial.println("HTTP compatibility server started on port 80");
    }
}

void registerRoutes(WebServer& s) {
    s.on("/", HTTP_GET, [&s]() { handleRoot(s); });
    s.on("/send", HTTP_POST, [&s]() { handleSend(s); });
    s.on("/request", HTTP_POST, [&s]() { handleRequest(s); });
    s.on("/healthz", HTTP_GET, [&s]() { handleHealthz(s); });
}

void handleSend(WebServer& ctx) {
    // /send: fire-and-forget JSON to Mega
    if (!ctx.hasArg("plain")) {
        ctx.send(400, "application/json", "{\"ok\":false,\"error\":\"no payload\"}");
        return;
    }
    
    String payload = ctx.arg("plain");
    MegaUart.println(payload);
    
    ctx.send(200, "application/json", "{\"ok\":true}");
}

void handleRequest(WebServer& ctx) {
    // /request: send JSON to Mega and wait for response
    if (!ctx.hasArg("plain")) {
        ctx.send(400, "application/json", "{\"ok\":false,\"error\":\"no payload\"}");
        return;
    }
    
    String payload = ctx.arg("plain");
    StaticJsonDocument<256> reqDoc;
    String requestedCmd = "";
    if (deserializeJson(reqDoc, payload) == DeserializationError::Ok) {
        if (reqDoc["cmd"].is<const char*>()) {
            requestedCmd = reqDoc["cmd"].as<String>();
        }
    }

    g_responseReady = false;  // Clear previous response
    MegaUart.println(payload);
    
    // Wait for response with timeout (500ms)
    unsigned long startTime = millis();
    const unsigned long RESPONSE_TIMEOUT = 500;
    
    while ((millis() - startTime) < RESPONSE_TIMEOUT) {
        if (g_responseReady) {
            if (responseMatchesCommand(g_responseBuffer, requestedCmd)) {
                String response;
                serializeJson(g_responseBuffer, response);
                ctx.send(200, "application/json", response);
                g_responseReady = false;
                return;
            }
            // Ignore unrelated telemetry/event/heartbeat responses and keep waiting.
            g_responseReady = false;
        }
        delay(5);  // Small delay to allow other tasks
    }
    
    // Timeout: Mega didn't respond in time with a matching response
    ctx.send(504, "application/json", "{\"ok\":false,\"error\":\"timeout_waiting_for_mega_response\"}");
}

void handleHealthz(WebServer& ctx) {
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
    ctx.send(200, "application/json", response);
}

void handleRoot(WebServer& ctx) {
    ctx.send(200, "text/html", INDEX_HTML);
}

bool responseMatchesCommand(const JsonDocument& doc, const String& cmd) {
    if (cmd.length() == 0) return true;
    if (!doc["ok"].is<bool>() && !doc.containsKey("ok")) return false;
    if (doc["telemetry"].is<bool>() && doc["telemetry"].as<bool>()) return false;
    if (doc.containsKey("event") || doc.containsKey("info")) return false;

    if (cmd == "temp_read") return doc.containsKey("temps");
    if (cmd == "get_state") return doc.containsKey("pitch") && doc.containsKey("roll");
    if (cmd == "ultra_read") return doc.containsKey("cm");
    if (cmd == "rfid_last") return doc.containsKey("rfid");
    if (cmd == "imu_read") return doc.containsKey("msg");

    // For control commands, any non-telemetry/event json is acceptable.
    return true;
}
