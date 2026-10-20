// Workshop OS 12.3.10: fetches Local AI's cards (GET /api/display/feed) for the calm idle screen.
//
// One small HTTPS request a minute on a background task, backing off to 10 minutes while Local AI doesn't answer.
// The connection goes to Local AI's IP address and checks its certificate against Local AI's own CA and the name
// on the certificate (the ESP32's mbedTLS 2.28 can't match IP addresses in certificates). The display key signs
// it in for this one route. The key and CA are kept in NVS ("ws12-lai") and are never sent back by the portal.

#include "workshop_localai_feed.h"

#include <Arduino.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>

#include <cstring>

#include <nvs.h>

namespace {

using workshop::localai::Card;
namespace lai = workshop::localai;

constexpr char kNamespace[] = "ws12-lai";
constexpr size_t kMaxCaBytes = 4096;
constexpr size_t kMaxBodyBytes = 8192;

portMUX_TYPE g_mux = portMUX_INITIALIZER_UNLOCKED;
WorkshopLocalAiFeedSnapshot g_snap;
char g_address[16] = {};
char g_tlsName[64] = {};
char g_key[56] = {};
char* g_ca = nullptr;  // PSRAM or heap, kMaxCaBytes
std::uint32_t g_generation = 0;
std::uint32_t g_nextAtMs = 0;
bool g_taskActive = false;

void copyText(char* out, size_t len, const char* in) {
    if (!out || !len) return;
    strlcpy(out, in ? in : "", len);
}

void setStatus(const char* msg) {
    portENTER_CRITICAL(&g_mux);
    copyText(g_snap.status, sizeof(g_snap.status), msg);
    portEXIT_CRITICAL(&g_mux);
}

bool ensureCaBuffer() {
    if (g_ca) return true;
    g_ca = static_cast<char*>(ps_malloc(kMaxCaBytes));
    if (!g_ca) g_ca = static_cast<char*>(malloc(kMaxCaBytes));
    if (g_ca) g_ca[0] = 0;
    return g_ca != nullptr;
}

bool configuredLocked() {
    return lai::validPrivateIp(g_address) && lai::validTlsName(g_tlsName) && lai::validKey(g_key) && g_ca && g_ca[0];
}

// One HTTP/1.0 request, so the answer is a plain body until the connection closes (HTTP/1.1 comes back chunked
// through Caddy): status line and headers, then the body into a JSON document.
bool fetch(Card* cards, std::uint8_t& count, char* error, size_t errorLen) {
    count = 0;
    if (WiFi.status() != WL_CONNECTED) { copyText(error, errorLen, "Waiting for Wi-Fi."); return false; }
    char address[16], name[64], key[56];
    static char ca[kMaxCaBytes];
    portENTER_CRITICAL(&g_mux);
    memcpy(address, g_address, sizeof(address));
    memcpy(name, g_tlsName, sizeof(name));
    memcpy(key, g_key, sizeof(key));
    copyText(ca, sizeof(ca), g_ca);
    portEXIT_CRITICAL(&g_mux);

    IPAddress ip;
    if (!ip.fromString(address)) { copyText(error, errorLen, "Local AI's address is not valid."); return false; }
    WiFiClientSecure client;
    client.setHandshakeTimeout(10);  // seconds
    if (!client.connect(ip, 443, name, ca, nullptr, nullptr)) {
        copyText(error, errorLen, "Local AI isn't answering, or its certificate didn't match.");
        memset(key, 0, sizeof(key));
        return false;
    }
    client.printf("GET /api/display/feed HTTP/1.0\r\nHost: %s\r\nUser-Agent: Workshop-Display/12 ESP32HTTPClient\r\n"
                  "Accept: application/json\r\nX-LocalAI-Display-Key: %s\r\nConnection: close\r\n\r\n", name, key);
    memset(key, 0, sizeof(key));

    // Wait for the first bytes of the answer (Stream reads give up after 1 s; Local AI may take longer to start).
    const std::uint32_t sentAt = millis();
    while (!client.available() && client.connected() && millis() - sentAt < 8000UL) delay(10);
    const String statusLine = client.readStringUntil('\n');
    int code = 0;
    if (statusLine.startsWith("HTTP/1.")) code = statusLine.substring(9, 12).toInt();
    size_t contentLength = 0;
    for (;;) {
        const String line = client.readStringUntil('\n');
        if (line.length() <= 1) break;  // "\r" ends the headers
        if (line.startsWith("Content-Length:") || line.startsWith("content-length:")) contentLength = (size_t)line.substring(15).toInt();
    }
    if (code != 200) {
        snprintf(error, errorLen, code == 401 || code == 403 ? "Local AI turned the display key down (HTTP %d)." : "Local AI answered HTTP %d.", code);
        client.stop();
        return false;
    }
    if (contentLength > kMaxBodyBytes) { copyText(error, errorLen, "Local AI's answer was too large."); client.stop(); return false; }

    JsonDocument doc;
    const DeserializationError err = deserializeJson(doc, client);
    client.stop();
    if (err) { copyText(error, errorLen, "Local AI's answer was not valid JSON."); return false; }
    for (JsonObject c : doc["cards"].as<JsonArray>()) {
        const char* kind = c["kind"] | "";
        if (!lai::shownKind(kind) || count >= lai::kMaxCards) continue;
        Card& out = cards[count++];
        copyText(out.kind, sizeof(out.kind), kind);
        copyText(out.title, sizeof(out.title), c["title"] | "");
        copyText(out.text, sizeof(out.text), c["text"] | "");
        out.tone = lai::toneFrom(c["tone"] | "");
    }
    return true;
}

void fetchTask(void*) {
    static Card cards[lai::kMaxCards];
    std::uint8_t count = 0;
    char error[96] = {};
    portENTER_CRITICAL(&g_mux);
    const std::uint32_t generation = g_generation;
    portEXIT_CRITICAL(&g_mux);
    const bool ok = fetch(cards, count, error, sizeof(error));
    const std::uint32_t now = millis();
    portENTER_CRITICAL(&g_mux);
    if (generation == g_generation) {  // never publish cards fetched under settings that changed meanwhile
        g_snap.lastAttemptAtMs = now;
        if (ok) {
            memcpy(g_snap.cards, cards, sizeof(cards));
            g_snap.count = count;
            g_snap.lastSuccessAtMs = now;
            g_snap.failures = 0;
            copyText(g_snap.status, sizeof(g_snap.status), "Local AI cards are current.");
        } else {
            if (g_snap.failures < 8) ++g_snap.failures;
            copyText(g_snap.status, sizeof(g_snap.status), error);
        }
        g_nextAtMs = now + lai::nextDelayMs(g_snap.failures);
    }
    g_snap.busy = false;
    g_taskActive = false;
    portEXIT_CRITICAL(&g_mux);
    vTaskDelete(nullptr);
}

}  // namespace

void workshopLocalAiFeedBegin() {
    if (!ensureCaBuffer()) return;
    Preferences prefs;
    if (prefs.begin(kNamespace, true)) {
        copyText(g_address, sizeof(g_address), prefs.getString("addr", "").c_str());
        copyText(g_tlsName, sizeof(g_tlsName), prefs.getString("name", "").c_str());
        copyText(g_key, sizeof(g_key), prefs.getString("key", "").c_str());
        copyText(g_ca, kMaxCaBytes, prefs.getString("ca", "").c_str());
        prefs.end();
    }
    portENTER_CRITICAL(&g_mux);
    g_snap = WorkshopLocalAiFeedSnapshot{};
    g_snap.configured = configuredLocked();
    copyText(g_snap.status, sizeof(g_snap.status), g_snap.configured ? "Waiting for the first Local AI cards." : "Local AI cards are not set up.");
    g_nextAtMs = millis() + 15000UL;  // let Wi-Fi and the clock settle first
    portEXIT_CRITICAL(&g_mux);
}

void workshopLocalAiFeedLoop() {
    const std::uint32_t now = millis();
    portENTER_CRITICAL(&g_mux);
    const bool due = g_snap.configured && !g_taskActive && (std::int32_t)(now - g_nextAtMs) >= 0;
    if (due) { g_taskActive = true; g_snap.busy = true; }
    portEXIT_CRITICAL(&g_mux);
    if (!due) return;
    if (xTaskCreatePinnedToCore(fetchTask, "ws12LocalAi", 12288, nullptr, 1, nullptr, 0) != pdPASS) {
        portENTER_CRITICAL(&g_mux);
        g_taskActive = false;
        g_snap.busy = false;
        g_nextAtMs = now + lai::kPollMs;
        portEXIT_CRITICAL(&g_mux);
        setStatus("Could not start the Local AI request.");
    }
}

bool workshopLocalAiFeedConfigure(const char* address, const char* tlsName, const char* key, const char* caPem) {
    if (!lai::validPrivateIp(address) || !lai::validTlsName(tlsName) || !lai::validKey(key) ||
        !caPem || strlen(caPem) >= kMaxCaBytes || !strstr(caPem, "-----BEGIN CERTIFICATE-----")) {
        setStatus("Not saved: the address, certificate name, key or CA is not valid.");
        return false;
    }
    if (!ensureCaBuffer()) return false;
    // Save all four or none: a put that fails (NVS full) must not leave a half-saved setting that only works until
    // the next restart.
    Preferences prefs;
    if (!prefs.begin(kNamespace, false)) { setStatus("Could not open the settings storage."); return false; }
    const bool saved = prefs.putString("addr", address) == strlen(address) && prefs.putString("name", tlsName) == strlen(tlsName) &&
                       prefs.putString("key", key) == strlen(key) && prefs.putString("ca", caPem) == strlen(caPem);
    if (!saved) prefs.clear();
    prefs.end();
    if (!saved) {
        char msg[96];
        snprintf(msg, sizeof(msg), "Could not save: settings storage is full (%u free entries).", (unsigned)workshopLocalAiFeedNvsFreeEntries());
        setStatus(msg);
        return false;
    }
    portENTER_CRITICAL(&g_mux);
    copyText(g_address, sizeof(g_address), address);
    copyText(g_tlsName, sizeof(g_tlsName), tlsName);
    copyText(g_key, sizeof(g_key), key);
    copyText(g_ca, kMaxCaBytes, caPem);
    ++g_generation;
    g_snap.configured = true;
    g_snap.count = 0;
    g_snap.failures = 0;
    g_nextAtMs = millis();
    copyText(g_snap.status, sizeof(g_snap.status), "Saved. Asking Local AI for cards.");
    portEXIT_CRITICAL(&g_mux);
    return true;
}

void workshopLocalAiFeedClear() {
    Preferences prefs;
    if (prefs.begin(kNamespace, false)) { prefs.clear(); prefs.end(); }
    portENTER_CRITICAL(&g_mux);
    memset(g_key, 0, sizeof(g_key));
    g_address[0] = g_tlsName[0] = 0;
    if (g_ca) g_ca[0] = 0;
    ++g_generation;
    g_snap = WorkshopLocalAiFeedSnapshot{};
    copyText(g_snap.status, sizeof(g_snap.status), "Local AI cards are not set up.");
    portEXIT_CRITICAL(&g_mux);
}

std::size_t workshopLocalAiFeedNvsFreeEntries() {
    nvs_stats_t st;
    return nvs_get_stats(nullptr, &st) == ESP_OK ? st.free_entries : 0;
}

WorkshopLocalAiFeedSnapshot workshopLocalAiFeedSnapshot() {
    portENTER_CRITICAL(&g_mux);
    WorkshopLocalAiFeedSnapshot s = g_snap;
    portEXIT_CRITICAL(&g_mux);
    return s;
}
