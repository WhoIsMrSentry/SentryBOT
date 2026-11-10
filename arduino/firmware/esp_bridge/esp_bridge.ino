#include <WiFi.h>
#include <ESPmDNS.h>
#include <WebServer.h>
#include <ArduinoJson.h>
#include <math.h>
#include <string.h>

#include "config.h"
#include "index.h"
#include "RobotState.h"
#include "UartHandler.h"

HardwareSerial MegaUart(2);
RobotState g_robotState;
WebServer server(HTTP_PORT);
WebServer serverCompat80(80);

static bool s_mdnsStarted = false;

// Forward declarations
void setupWiFi();
void ensureMdnsStarted();
void setupWebServer();
void registerRoutes(WebServer& s);
bool checkBridgeAuth(WebServer& ctx);
bool prepareCleanJsonLine(const String& raw, String& cleanLine, JsonDocument& reqDoc);
void handleSend(WebServer& ctx);
void handleRequest(WebServer& ctx);
void handleHealthz(WebServer& ctx);
void handleState(WebServer& ctx);
void handleRoot(WebServer& ctx);
bool responseMatchesCommand(const JsonDocument& doc, const String& cmd, bool hasSeq, long reqSeq);

void setup() {
    Serial.begin(115200);
    Serial.println("\n\nSentryBOT ESP Bridge Starting (RTOS Mode)...");

    // Start UART and Mega keepalive heartbeat BEFORE blocking WiFi connection
    initUartTask();
    initLinkTask();

    setupWiFi();
    setupWebServer();

    Serial.println("Bridge Tasks Initialized.");
}

void loop() {
    if (WiFi.status() == WL_CONNECTED) {
        if (!s_mdnsStarted) {
            ensureMdnsStarted();
        }
        server.handleClient();
        if (HTTP_PORT != 80) {
            serverCompat80.handleClient();
        }
    }
    vTaskDelay(pdMS_TO_TICKS(5));
}

void ensureMdnsStarted() {
    if (s_mdnsStarted) return;
    if (!MDNS.begin(MDNS_HOSTNAME)) {
        Serial.println("MDNS initialization failed");
        return;
    }
    s_mdnsStarted = true;
    Serial.print("mDNS initialized as: ");
    Serial.print(MDNS_HOSTNAME);
    Serial.println(".local");
    MDNS.addService("http", "tcp", HTTP_PORT);
}

void setupWiFi() {
    if (strlen(WIFI_SSID) == 0) {
        Serial.println("WIFI_SSID empty (configure local_config.h). Running UART-only mode.");
        return;
    }

    Serial.print("Connecting to WiFi: ");
    Serial.println(WIFI_SSID);

    WiFi.mode(WIFI_STA);
    WiFi.setSleep(WIFI_PS_NONE);
    WiFi.setAutoReconnect(true);
    WiFi.begin(WIFI_SSID, WIFI_PASS);

    int retry = 0;
    const int MAX_RETRY = 20; // 10 seconds

    while (WiFi.status() != WL_CONNECTED && retry < MAX_RETRY) {
        delay(500);
        Serial.print(".");
        retry++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println();
        Serial.print("WiFi Connected! IP: ");
        Serial.println(WiFi.localIP());
        ensureMdnsStarted();
    } else {
        Serial.println();
        Serial.println("WiFi connection timed out at boot; auto-reconnect active.");
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
    const char* authHeaders[] = { "X-API-Key", "Authorization" };
    s.collectHeaders(authHeaders, 2);
    s.on("/", HTTP_GET, [&s]() { handleRoot(s); });
    s.on("/send", HTTP_POST, [&s]() { handleSend(s); });
    s.on("/request", HTTP_POST, [&s]() { handleRequest(s); });
    s.on("/healthz", HTTP_GET, [&s]() { handleHealthz(s); });
    s.on("/state", HTTP_GET, [&s]() { handleState(s); });
}

static bool constantTimeEquals(const String& a, const char* b) {
    size_t blen = b ? strlen(b) : 0;
    if (a.length() != blen) return false;
    uint8_t diff = 0;
    for (size_t i = 0; i < blen; i++) {
        diff |= (uint8_t)(a[i] ^ b[i]);
    }
    return diff == 0;
}

bool checkBridgeAuth(WebServer& ctx) {
    const char* expected = BRIDGE_AUTH_TOKEN;
    if (!expected || expected[0] == '\0') return true;

    if (ctx.hasHeader("X-API-Key") && constantTimeEquals(ctx.header("X-API-Key"), expected)) {
        return true;
    }
    if (ctx.hasHeader("Authorization")) {
        String auth = ctx.header("Authorization");
        if (auth.startsWith("Bearer ") && constantTimeEquals(auth.substring(7), expected)) {
            return true;
        }
    }
    ctx.send(401, "application/json", "{\"ok\":false,\"error\":\"unauthorized\"}");
    return false;
}

bool prepareCleanJsonLine(const String& raw, String& cleanLine, JsonDocument& reqDoc) {
    if (raw.length() == 0 || raw.length() >= SERIAL_BUF_SIZE - 4) return false;
    reqDoc.clear();
    DeserializationError err = deserializeJson(reqDoc, raw);
    if (err || !reqDoc.is<JsonObject>()) return false;

    cleanLine = "";
    serializeJson(reqDoc, cleanLine);
    if (cleanLine.length() == 0 || cleanLine.length() >= SERIAL_BUF_SIZE - 4) return false;
    if (cleanLine.indexOf('\n') >= 0 || cleanLine.indexOf('\r') >= 0) return false;
    return true;
}

void handleSend(WebServer& ctx) {
    if (!checkBridgeAuth(ctx)) return;
    if (!ctx.hasArg("plain")) {
        ctx.send(400, "application/json", "{\"ok\":false,\"error\":\"no payload\"}");
        return;
    }

    StaticJsonDocument<512> reqDoc;
    String cleanLine;
    if (!prepareCleanJsonLine(ctx.arg("plain"), cleanLine, reqDoc)) {
        ctx.send(400, "application/json", "{\"ok\":false,\"error\":\"invalid_json\"}");
        return;
    }

    if (!uartSendLine(cleanLine)) {
        ctx.send(503, "application/json", "{\"ok\":false,\"error\":\"uart_tx_busy\"}");
        return;
    }

    ctx.send(200, "application/json", "{\"ok\":true}");
}

void handleRequest(WebServer& ctx) {
    if (!checkBridgeAuth(ctx)) return;
    if (!ctx.hasArg("plain")) {
        ctx.send(400, "application/json", "{\"ok\":false,\"error\":\"no payload\"}");
        return;
    }

    StaticJsonDocument<512> reqDoc;
    String cleanLine;
    if (!prepareCleanJsonLine(ctx.arg("plain"), cleanLine, reqDoc)) {
        ctx.send(400, "application/json", "{\"ok\":false,\"error\":\"invalid_json\"}");
        return;
    }

    String requestedCmd = "";
    if (reqDoc["cmd"].is<const char*>()) {
        requestedCmd = reqDoc["cmd"].as<String>();
    }
    bool hasSeq = !reqDoc["seq"].isNull();
    long reqSeq = hasSeq ? reqDoc["seq"].as<long>() : -1L;

    unsigned long timeoutMs = 500;
    if (ctx.hasArg("timeout")) {
        float sec = ctx.arg("timeout").toFloat();
        if (sec > 0.0f) {
            long ms = lroundf(sec * 1000.0f);
            timeoutMs = (unsigned long)constrain(ms, 50L, 5000L);
        }
    } else if (ctx.hasArg("timeout_ms")) {
        long ms = ctx.arg("timeout_ms").toInt();
        if (ms > 0) {
            timeoutMs = (unsigned long)constrain(ms, 50L, 5000L);
        }
    }

    uartBeginResponseWindow();
    if (!uartSendLine(cleanLine)) {
        uartEndResponseWindow();
        ctx.send(503, "application/json", "{\"ok\":false,\"error\":\"uart_tx_busy\"}");
        return;
    }

    unsigned long startTime = millis();
    char rxBuf[SERIAL_BUF_SIZE];
    StaticJsonDocument<JSON_DOC_SIZE> respDoc;

    while ((millis() - startTime) < timeoutMs) {
        if (uartReceiveResponseLine(rxBuf, sizeof(rxBuf), pdMS_TO_TICKS(10))) {
            respDoc.clear();
            DeserializationError err = deserializeJson(respDoc, rxBuf);
            if (!err && respDoc.is<JsonObject>() && responseMatchesCommand(respDoc, requestedCmd, hasSeq, reqSeq)) {
                String response;
                serializeJson(respDoc, response);
                uartEndResponseWindow();
                ctx.send(200, "application/json", response);
                return;
            }
        }
    }

    uartEndResponseWindow();
    ctx.send(504, "application/json", "{\"ok\":false,\"error\":\"timeout_waiting_for_mega_response\"}");
}

void handleHealthz(WebServer& ctx) {
    RobotData st = g_robotState.get();
    bool wifiOk = (WiFi.status() == WL_CONNECTED);

    StaticJsonDocument<384> doc;
    doc["ok"] = st.link_alive && wifiOk;
    doc["wifi"] = wifiOk;
    doc["link"] = st.link_alive;
    doc["link_alive"] = st.link_alive;
    doc["uptime_ms"] = (uint32_t)millis();
    doc["last_update_ms"] = st.last_update_ms;
    doc["uart_rx_errors"] = st.uart_rx_errors;
    doc["uart_overflows"] = st.uart_overflows;
    doc["rssi"] = wifiOk ? WiFi.RSSI() : 0;

    String response;
    serializeJson(doc, response);
    ctx.send(200, "application/json", response);
}

void handleState(WebServer& ctx) {
    RobotData st = g_robotState.get();

    StaticJsonDocument<1024> doc;
    doc["ok"] = st.link_alive;
    doc["link_alive"] = st.link_alive;
    doc["uptime_ms"] = (uint32_t)millis();
    doc["last_update_ms"] = st.last_update_ms;
    doc["mode"] = st.mode;
    doc["estop"] = st.estop;
    doc["i2c_errors"] = st.i2c_errors;
    doc["pitch"] = st.pitch;
    doc["roll"] = st.roll;
    if (isnan(st.ultra_cm)) doc["ultra_cm"] = nullptr;
    else doc["ultra_cm"] = st.ultra_cm;
    doc["rfid"] = st.last_rfid;

    JsonArray poseArr = doc.createNestedArray("pose");
    for (int i = 0; i < 4; i++) poseArr.add(st.pose[i]);

    JsonArray stepArr = doc.createNestedArray("stepper_pos");
    for (int i = 0; i < 2; i++) stepArr.add(st.stepper_pos[i]);

    JsonArray tempArr = doc.createNestedArray("temps");
    for (int i = 0; i < 8; i++) {
        if (isnan(st.temps[i])) tempArr.add(nullptr);
        else tempArr.add(st.temps[i]);
    }

    doc["uart_rx_errors"] = st.uart_rx_errors;
    doc["uart_overflows"] = st.uart_overflows;

    String response;
    serializeJson(doc, response);
    ctx.send(200, "application/json", response);
}

void handleRoot(WebServer& ctx) {
    ctx.send(200, "text/html", INDEX_HTML);
}

bool responseMatchesCommand(const JsonDocument& doc, const String& cmd, bool hasSeq, long reqSeq) {
    if (!doc.containsKey("ok") && !doc.containsKey("err")) return false;
    if (doc["telemetry"].is<bool>() && doc["telemetry"].as<bool>()) return false;
    if (doc.containsKey("event") || doc.containsKey("info") || doc.containsKey("evt") || doc.containsKey("warn")) return false;

    // Ignore background heartbeat replies unless the caller explicitly asked for "hb".
    if (doc["msg"].is<const char*>() && strcmp(doc["msg"].as<const char*>(), "hb") == 0 && cmd != "hb") {
        return false;
    }

    if (hasSeq) {
        long gotSeq = -1L;
        if (!doc["seq"].isNull()) gotSeq = doc["seq"].as<long>();
        else if (!doc["ack_seq"].isNull()) gotSeq = doc["ack_seq"].as<long>();
        if (gotSeq != reqSeq) return false;
    }

    if (cmd.length() == 0) return true;
    if (cmd == "temp_read") return doc.containsKey("temps");
    if (cmd == "get_state") return doc.containsKey("pitch") && doc.containsKey("roll");
    if (cmd == "ultra_read") return doc.containsKey("cm");
    if (cmd == "rfid_last") return doc.containsKey("rfid");
    if (cmd == "imu_read") return doc.containsKey("msg") || doc.containsKey("pitch");

    return true;
}
