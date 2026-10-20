// Workshop OS 12.3.10: fetches Local AI's cards (GET /api/display/feed) for the calm idle screen.
//
// One small HTTPS request a minute on a background task, backing off to 10 minutes while Local AI doesn't answer.
// The connection goes to Local AI's IP address and checks its certificate against Local AI's own CA and the name
// on the certificate (the ESP32's mbedTLS 2.28 can't match IP addresses in certificates). The display key signs
// it in for this one route. The settings, key and CA are kept in /localai.json on LittleFS, on the flash's spare
// "spiffs" partition (NVS is nearly full on the WS350: a 600-byte CA did not fit), and are never sent back by the
// portal.
//
// 12.4.2: the same task answers the Local AI tab's ask buttons (GET /api/display/ask) and downloads the feed's latest
// image (a JPEG, into PSRAM), one request at a time.

#include "workshop_localai_feed.h"

#include <Arduino.h>
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>

#include <cstdint>
#include <cstring>

#include <nvs.h>

namespace {

using workshop::localai::Card;
namespace lai = workshop::localai;

constexpr char kSettingsPath[] = "/localai.json";
bool g_fsReady = false;
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

// 12.4.2: ask buttons and the latest image share the feed's task, one request at a time.
enum class Job : std::uint8_t { Feed, Ask, Image };
WorkshopLocalAiExtras g_extras;
char g_askPending[12] = {};        // a question waiting for the task
bool g_imagePending = false;
char g_imagePath[lai::kImagePathLen] = {};  // the feed's latest image (validImagePath)
char g_imageLoaded[lai::kImagePathLen] = {};  // the one in g_image (12.4.3: not downloaded again)
std::uint8_t* g_image = nullptr;   // PSRAM, kMaxImageBytes
std::size_t g_imageLen = 0;

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

// One HTTP/1.0 GET, so the answer is a plain body until the connection closes (HTTP/1.1 comes back chunked through
// Caddy). Sends the request with the display key and reads the status line and headers; on HTTP 200 the body is
// next on `client`. False with `error` set otherwise (the connection is closed then).
bool openGet(WiFiClientSecure& client, const char* path, const char* accept, size_t& contentLength, char* contentType,
             size_t contentTypeLen, char* error, size_t errorLen) {
    contentLength = 0;
    if (contentType && contentTypeLen) contentType[0] = 0;
    if (WiFi.status() != WL_CONNECTED) { copyText(error, errorLen, "Waiting for Wi-Fi."); return false; }
    char address[16], name[64], key[56];
    static char ca[kMaxCaBytes];  // one request at a time (the task)
    portENTER_CRITICAL(&g_mux);
    memcpy(address, g_address, sizeof(address));
    memcpy(name, g_tlsName, sizeof(name));
    memcpy(key, g_key, sizeof(key));
    copyText(ca, sizeof(ca), g_ca);
    portEXIT_CRITICAL(&g_mux);

    IPAddress ip;
    if (!ip.fromString(address)) { copyText(error, errorLen, "Local AI's address is not valid."); memset(key, 0, sizeof(key)); return false; }
    client.setHandshakeTimeout(10);  // seconds
    if (!client.connect(ip, 443, name, ca, nullptr, nullptr)) {
        copyText(error, errorLen, "Local AI isn't answering, or its certificate didn't match.");
        memset(key, 0, sizeof(key));
        return false;
    }
    client.printf("GET %s HTTP/1.0\r\nHost: %s\r\nUser-Agent: Workshop-Display/12 ESP32HTTPClient\r\n"
                  "Accept: %s\r\nX-LocalAI-Display-Key: %s\r\nConnection: close\r\n\r\n", path, name, accept, key);
    memset(key, 0, sizeof(key));

    // Wait for the first bytes of the answer (Stream reads give up after 1 s; Local AI may take longer to start).
    const std::uint32_t sentAt = millis();
    while (!client.available() && client.connected() && millis() - sentAt < 8000UL) delay(10);
    const String statusLine = client.readStringUntil('\n');
    int code = 0;
    if (statusLine.startsWith("HTTP/1.")) code = statusLine.substring(9, 12).toInt();
    for (;;) {
        const String line = client.readStringUntil('\n');
        if (line.length() <= 1) break;  // "\r" ends the headers
        String lower = line;
        lower.toLowerCase();
        if (lower.startsWith("content-length:")) contentLength = (size_t)line.substring(15).toInt();
        else if (lower.startsWith("content-type:") && contentType && contentTypeLen) {
            String v = line.substring(13);
            v.trim();
            copyText(contentType, contentTypeLen, v.c_str());
        }
    }
    if (code != 200) {
        snprintf(error, errorLen, code == 401 || code == 403 ? "Local AI turned the display key down (HTTP %d)." : "Local AI answered HTTP %d.", code);
        client.stop();
        return false;
    }
    return true;
}

bool fetch(Card* cards, std::uint8_t& count, char* imagePath, char* imageTitle, char* imageText, std::uint32_t& imageAt,
           char* error, size_t errorLen) {
    count = 0;
    imagePath[0] = imageTitle[0] = imageText[0] = 0;
    imageAt = 0;
    WiFiClientSecure client;
    size_t contentLength = 0;
    if (!openGet(client, "/api/display/feed", "application/json", contentLength, nullptr, 0, error, errorLen)) return false;
    if (contentLength > kMaxBodyBytes) { copyText(error, errorLen, "Local AI's answer was too large."); client.stop(); return false; }

    JsonDocument doc;
    const DeserializationError err = deserializeJson(doc, client);
    client.stop();
    if (err) { copyText(error, errorLen, "Local AI's answer was not valid JSON."); return false; }
    for (JsonObject c : doc["cards"].as<JsonArray>()) {
        const char* kind = c["kind"] | "";
        if (!strcmp(kind, "image") && !imagePath[0] && lai::validImagePath(c["imageUrl"] | "")) {
            copyText(imagePath, lai::kImagePathLen, c["imageUrl"] | "");
            copyText(imageTitle, lai::kTitleLen, c["title"] | "");
            copyText(imageText, lai::kTextLen, c["text"] | "");
            imageAt = c["at"] | 0U;
            continue;
        }
        if (!lai::shownKind(kind) || count >= lai::kMaxCards) continue;
        Card& out = cards[count++];
        copyText(out.kind, sizeof(out.kind), kind);
        copyText(out.title, sizeof(out.title), c["title"] | "");
        copyText(out.text, sizeof(out.text), c["text"] | "");
        out.tone = lai::toneFrom(c["tone"] | "");
    }
    return true;
}

bool ask(const char* question, char* answer, size_t answerLen) {
    char path[48];
    snprintf(path, sizeof(path), "/api/display/ask?q=%s", question);
    WiFiClientSecure client;
    size_t contentLength = 0;
    if (!openGet(client, path, "application/json", contentLength, nullptr, 0, answer, answerLen)) return false;
    if (contentLength > 1024) { copyText(answer, answerLen, "Local AI's answer was too large."); client.stop(); return false; }
    JsonDocument doc;
    const DeserializationError err = deserializeJson(doc, client);
    client.stop();
    const char* text = doc["answer"] | "";
    if (err || !text[0]) { copyText(answer, answerLen, "Local AI's answer was not valid."); return false; }
    copyText(answer, answerLen, text);
    return true;
}

// Reads the JPEG into g_image (the UI doesn't touch it while imageBusy).
bool downloadImage(const char* path, char* error, size_t errorLen) {
    g_imageLen = 0;
    if (!g_image) g_image = static_cast<std::uint8_t*>(ps_malloc(lai::kMaxImageBytes));
    if (!g_image) { copyText(error, errorLen, "No memory for the picture."); return false; }
    WiFiClientSecure client;
    size_t contentLength = 0;
    char type[40];
    if (!openGet(client, path, "image/jpeg", contentLength, type, sizeof(type), error, errorLen)) return false;
    if (strncmp(type, "image/jpeg", 10) != 0) { copyText(error, errorLen, "Local AI sent a picture the display can't draw."); client.stop(); return false; }
    // Caddy answers HTTP/1.0 without a length (the body ends when the connection closes): then read to the end.
    if (contentLength > lai::kMaxImageBytes) { copyText(error, errorLen, "The picture is too large for the display."); client.stop(); return false; }
    const size_t limit = contentLength ? contentLength : lai::kMaxImageBytes;
    std::uint32_t lastByteAt = millis();
    size_t got = 0;
    bool tooLarge = false;
    while (millis() - lastByteAt < 10000UL) {
        if (contentLength && got >= contentLength) break;
        const int avail = client.available();
        if (avail <= 0) {
            if (!client.connected()) break;
            delay(5);
            continue;
        }
        if (got >= limit) { tooLarge = true; break; }
        const size_t want = limit - got < (size_t)avail ? limit - got : (size_t)avail;
        const int n = client.read(g_image + got, want);
        if (n > 0) { got += (size_t)n; lastByteAt = millis(); }
    }
    client.stop();
    if (tooLarge) { copyText(error, errorLen, "The picture is too large for the display."); return false; }
    std::uint16_t w = 0, h = 0;
    // A whole JPEG ends with EOI (FF D9): without a length this is how a cut-off download shows.
    if (got < 4 || (contentLength && got != contentLength) || g_image[got - 2] != 0xFF || g_image[got - 1] != 0xD9) { copyText(error, errorLen, "The picture didn't finish downloading."); return false; }
    if (!lai::jpegSize(g_image, got, w, h)) { copyText(error, errorLen, "The picture is not a JPEG the display can draw."); return false; }
    g_imageLen = got;
    return true;
}

void fetchTask(void* arg) {
    const Job job = static_cast<Job>(reinterpret_cast<std::uintptr_t>(arg));
    char error[96] = {};
    portENTER_CRITICAL(&g_mux);
    const std::uint32_t generation = g_generation;
    portEXIT_CRITICAL(&g_mux);
    if (job == Job::Ask) {
        char question[12], answer[lai::kAnswerLen];
        portENTER_CRITICAL(&g_mux);
        copyText(question, sizeof(question), g_askPending);
        g_askPending[0] = 0;
        portEXIT_CRITICAL(&g_mux);
        const bool ok = ask(question, answer, sizeof(answer));
        portENTER_CRITICAL(&g_mux);
        g_extras.askOk = ok;
        copyText(g_extras.askAnswer, sizeof(g_extras.askAnswer), answer);
        ++g_extras.askSeq;
        g_extras.askBusy = false;
        g_taskActive = false;
        portEXIT_CRITICAL(&g_mux);
        vTaskDelete(nullptr);
    }
    if (job == Job::Image) {
        char path[lai::kImagePathLen];
        portENTER_CRITICAL(&g_mux);
        copyText(path, sizeof(path), g_imagePath);
        g_imagePending = false;
        portEXIT_CRITICAL(&g_mux);
        const bool ok = path[0] && downloadImage(path, error, sizeof(error));
        if (!path[0]) copyText(error, sizeof(error), "Local AI has no image yet.");
        portENTER_CRITICAL(&g_mux);
        copyText(g_imageLoaded, sizeof(g_imageLoaded), ok ? path : "");
        g_extras.imageReady = ok;
        copyText(g_extras.imageStatus, sizeof(g_extras.imageStatus), ok ? "" : error);
        ++g_extras.imageSeq;
        g_extras.imageBusy = false;
        g_taskActive = false;
        portEXIT_CRITICAL(&g_mux);
        vTaskDelete(nullptr);
    }
    static Card cards[lai::kMaxCards];
    static char imagePath[lai::kImagePathLen], imageTitle[lai::kTitleLen], imageText[lai::kTextLen];
    std::uint32_t imageAt = 0;
    std::uint8_t count = 0;
    const bool ok = fetch(cards, count, imagePath, imageTitle, imageText, imageAt, error, sizeof(error));
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
            copyText(g_imagePath, sizeof(g_imagePath), imagePath);
            g_extras.hasImage = imagePath[0] != 0;
            copyText(g_extras.imageTitle, sizeof(g_extras.imageTitle), imageTitle);
            copyText(g_extras.imageText, sizeof(g_extras.imageText), imageText);
            g_extras.imageAt = imageAt;
            // 12.4.3: a new picture is fetched now, in the background, so opening it is instant.
            if (imagePath[0] && strcmp(imagePath, g_imageLoaded) != 0 && !g_extras.imageBusy) {
                g_imagePending = true;
                g_extras.imageBusy = true;
                g_extras.imageStatus[0] = 0;
            }
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

// Mounts LittleFS on the "spiffs" partition (formatting it the first time), once.
bool mountSettings() {
    if (!g_fsReady) g_fsReady = LittleFS.begin(true, "/lfs", 4, "spiffs");
    return g_fsReady;
}

void workshopLocalAiFeedBegin() {
    if (!ensureCaBuffer()) return;
    if (mountSettings() && LittleFS.exists(kSettingsPath)) {
        File f = LittleFS.open(kSettingsPath, "r");
        JsonDocument doc;
        if (f && !deserializeJson(doc, f)) {
            copyText(g_address, sizeof(g_address), doc["address"] | "");
            copyText(g_tlsName, sizeof(g_tlsName), doc["name"] | "");
            copyText(g_key, sizeof(g_key), doc["key"] | "");
            copyText(g_ca, kMaxCaBytes, doc["ca"] | "");
        }
        if (f) f.close();
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
    // A question first, then the picture, then the cards when they are due.
    Job job = Job::Feed;
    portENTER_CRITICAL(&g_mux);
    bool due = false;
    if (g_snap.configured && !g_taskActive) {
        if (g_askPending[0]) { job = Job::Ask; due = true; }
        else if (g_imagePending) { job = Job::Image; due = true; }
        else if ((std::int32_t)(now - g_nextAtMs) >= 0) { due = true; g_snap.busy = true; }
    }
    if (due) g_taskActive = true;
    portEXIT_CRITICAL(&g_mux);
    if (!due) return;
    if (xTaskCreatePinnedToCore(fetchTask, "ws12LocalAi", 12288, reinterpret_cast<void*>(static_cast<std::uintptr_t>(job)), 1, nullptr, 0) != pdPASS) {
        portENTER_CRITICAL(&g_mux);
        g_taskActive = false;
        if (job == Job::Feed) { g_snap.busy = false; g_nextAtMs = now + lai::kPollMs; }
        else if (job == Job::Ask) { g_askPending[0] = 0; g_extras.askBusy = false; g_extras.askOk = false; copyText(g_extras.askAnswer, sizeof(g_extras.askAnswer), "Could not start the request."); ++g_extras.askSeq; }
        else { g_imagePending = false; g_extras.imageBusy = false; copyText(g_extras.imageStatus, sizeof(g_extras.imageStatus), "Could not start the download."); ++g_extras.imageSeq; }
        portEXIT_CRITICAL(&g_mux);
        if (job == Job::Feed) setStatus("Could not start the Local AI request.");
    }
}

bool workshopLocalAiFeedConfigure(const char* address, const char* tlsName, const char* key, const char* caPem) {
    if (!lai::validPrivateIp(address) || !lai::validTlsName(tlsName) || !lai::validKey(key) ||
        !caPem || strlen(caPem) >= kMaxCaBytes || !strstr(caPem, "-----BEGIN CERTIFICATE-----")) {
        setStatus("Not saved: the address, certificate name, key or CA is not valid.");
        return false;
    }
    if (!ensureCaBuffer()) return false;
    // Write a new file, then rename it over the old one, so a power cut never leaves half the settings.
    if (!mountSettings()) { setStatus("Could not save: the settings storage could not be opened."); return false; }
    JsonDocument doc;
    doc["address"] = address;
    doc["name"] = tlsName;
    doc["key"] = key;
    doc["ca"] = caPem;
    File f = LittleFS.open("/localai.tmp", "w");
    const size_t want = measureJson(doc);
    const bool written = f && serializeJson(doc, f) == want;
    if (f) f.close();
    if (!written || !LittleFS.rename("/localai.tmp", kSettingsPath)) {
        LittleFS.remove("/localai.tmp");
        setStatus("Could not save the settings file.");
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
    if (mountSettings()) LittleFS.remove(kSettingsPath);
    portENTER_CRITICAL(&g_mux);
    memset(g_key, 0, sizeof(g_key));
    g_address[0] = g_tlsName[0] = 0;
    if (g_ca) g_ca[0] = 0;
    ++g_generation;
    g_snap = WorkshopLocalAiFeedSnapshot{};
    copyText(g_snap.status, sizeof(g_snap.status), "Local AI cards are not set up.");
    g_imagePath[0] = g_imageLoaded[0] = 0;
    g_extras.hasImage = false;
    g_extras.imageReady = false;
    portEXIT_CRITICAL(&g_mux);
}

bool workshopLocalAiFeedAsk(const char* question) {
    if (!lai::validQuestion(question)) return false;
    portENTER_CRITICAL(&g_mux);
    const bool ok = g_snap.configured && !g_extras.askBusy;
    if (ok) {
        copyText(g_askPending, sizeof(g_askPending), question);
        copyText(g_extras.askQuestion, sizeof(g_extras.askQuestion), question);
        g_extras.askAnswer[0] = 0;
        g_extras.askBusy = true;
    }
    portEXIT_CRITICAL(&g_mux);
    return ok;
}

bool workshopLocalAiFeedFetchImage() {
    portENTER_CRITICAL(&g_mux);
    if (g_extras.imageReady && !g_extras.imageBusy && !strcmp(g_imagePath, g_imageLoaded)) {  // already here
        portEXIT_CRITICAL(&g_mux);
        return true;
    }
    const bool ok = g_snap.configured && g_extras.hasImage && !g_extras.imageBusy;
    if (ok) {
        g_imagePending = true;
        g_extras.imageBusy = true;
        g_extras.imageReady = false;
        g_extras.imageStatus[0] = 0;
    }
    portEXIT_CRITICAL(&g_mux);
    return ok;
}

WorkshopLocalAiExtras workshopLocalAiFeedExtras() {
    portENTER_CRITICAL(&g_mux);
    WorkshopLocalAiExtras e = g_extras;
    portEXIT_CRITICAL(&g_mux);
    return e;
}

bool workshopLocalAiFeedImage(const std::uint8_t** data, std::size_t* len) {
    portENTER_CRITICAL(&g_mux);
    const bool ok = g_extras.imageReady && !g_extras.imageBusy && g_image && g_imageLen;
    portEXIT_CRITICAL(&g_mux);
    if (!ok || !data || !len) return false;
    *data = g_image;
    *len = g_imageLen;
    return true;
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
