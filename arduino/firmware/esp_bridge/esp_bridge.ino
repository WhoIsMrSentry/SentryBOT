#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoJson.h>

// Network defaults requested for production profile.
static const char* WIFI_SSID = "SentryBOT";
static const char* WIFI_PASS = "SentryBOT";

// ESP32 UART2 -> Mega UART1 wiring
// ESP32 TX2(GPIO17) -> Mega RX1(pin 19)
// ESP32 RX2(GPIO16) -> Mega TX1(pin 18)
static const int UART_RX_PIN = 16;
static const int UART_TX_PIN = 17;
static const uint32_t UART_BAUD = 115200;

HardwareSerial MegaUart(2);
WebServer server(80);

String g_lastMegaLine;
unsigned long g_lastMegaTs = 0;

static bool readMegaLine(String &out, uint32_t timeoutMs) {
  unsigned long start = millis();
  String buf;
  while ((millis() - start) < timeoutMs) {
    while (MegaUart.available()) {
      char c = (char)MegaUart.read();
      if (c == '\r') continue;
      if (c == '\n') {
        out = buf;
        return out.length() > 0;
      }
      buf += c;
      if (buf.length() > 512) {
        buf = "";
      }
    }
    delay(1);
  }
  return false;
}

static bool forwardJsonToMega(const String &body, String &err) {
  DynamicJsonDocument doc(1024);
  DeserializationError de = deserializeJson(doc, body);
  if (de) {
    err = String("bad_json: ") + de.c_str();
    return false;
  }
  if (!doc.is<JsonObject>()) {
    err = "payload_must_be_object";
    return false;
  }

  String line;
  serializeJson(doc, line);
  MegaUart.print(line);
  MegaUart.print('\n');
  return true;
}

static uint32_t parseTimeoutMs(float fallbackSec) {
  if (!server.hasArg("timeout")) {
    return (uint32_t)(fallbackSec * 1000.0f);
  }
  float v = server.arg("timeout").toFloat();
  if (v <= 0.0f) v = fallbackSec;
  if (v > 20.0f) v = 20.0f;
  return (uint32_t)(v * 1000.0f);
}

static void handleHealthz() {
  DynamicJsonDocument out(512);
  out["ok"] = true;
  out["ssid"] = WiFi.SSID();
  out["ip"] = WiFi.localIP().toString();
  out["rssi"] = WiFi.RSSI();
  out["last_mega_ts_ms"] = g_lastMegaTs;
  out["last_mega_line"] = g_lastMegaLine;

  String body;
  serializeJson(out, body);
  server.send(200, "application/json", body);
}

static void handleSend() {
  if (!server.hasArg("plain")) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"missing_body\"}");
    return;
  }

  String err;
  if (!forwardJsonToMega(server.arg("plain"), err)) {
    String body = String("{\"ok\":false,\"error\":\"") + err + "\"}";
    server.send(400, "application/json", body);
    return;
  }

  server.send(200, "application/json", "{\"ok\":true}");
}

static void handleRequest() {
  if (!server.hasArg("plain")) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"missing_body\"}");
    return;
  }

  String err;
  if (!forwardJsonToMega(server.arg("plain"), err)) {
    String body = String("{\"ok\":false,\"error\":\"") + err + "\"}";
    server.send(400, "application/json", body);
    return;
  }

  uint32_t timeoutMs = parseTimeoutMs(1.2f);
  String line;
  if (!readMegaLine(line, timeoutMs)) {
    server.send(504, "application/json", "{\"ok\":false,\"error\":\"mega_timeout\"}");
    return;
  }

  g_lastMegaLine = line;
  g_lastMegaTs = millis();

  DynamicJsonDocument respDoc(1024);
  DeserializationError de = deserializeJson(respDoc, line);
  if (de || !respDoc.is<JsonObject>()) {
    DynamicJsonDocument out(256);
    out["ok"] = false;
    out["error"] = "mega_invalid_json";
    out["raw"] = line;
    String body;
    serializeJson(out, body);
    server.send(502, "application/json", body);
    return;
  }

  DynamicJsonDocument out(1536);
  out["ok"] = true;
  out["resp"] = respDoc.as<JsonObject>();
  String body;
  serializeJson(out, body);
  server.send(200, "application/json", body);
}

void setup() {
  Serial.begin(115200);
  MegaUart.begin(UART_BAUD, SERIAL_8N1, UART_RX_PIN, UART_TX_PIN);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - start) < 15000) {
    delay(200);
  }

  server.on("/healthz", HTTP_GET, handleHealthz);
  server.on("/send", HTTP_POST, handleSend);
  server.on("/request", HTTP_POST, handleRequest);
  server.begin();
}

void loop() {
  server.handleClient();
}
