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
//
// 12.6 (Local AI feed v2, LocalAI docs/WORKSHOP-DISPLAY.md): cards carry id/at/ask; the last 6 pictures; messages
// (a banner, a chime, one action) that the UI takes one at a time; approvals listed and, when Local AI allows,
// decided; a heartbeat every 5 minutes; and, while nothing else is waiting, a long poll (GET /api/display/events)
// that brings news in about 2 s. The long poll gives way at once to a question, a picture or an approval. Still one
// request at a time: the jobs below, in that order of priority.

#include "workshop_localai_feed.h"

#include <Arduino.h>
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>

#include <cstdint>
#include <cstring>
#include <ctime>

#include <nvs.h>

#if __has_include("smart_home_build.h")
#include "smart_home_build.h"
#endif
#ifndef WORKSHOP_OS_RELEASE_VERSION
#define WORKSHOP_OS_RELEASE_VERSION ""
#endif
#ifndef WORKSHOP_OS_SOURCE_SHA
#define WORKSHOP_OS_SOURCE_SHA ""
#endif

namespace {

using workshop::localai::Card;
namespace lai = workshop::localai;

constexpr char kSettingsPath[] = "/localai.json";
bool g_fsReady = false;
constexpr size_t kMaxCaBytes = 4096;
constexpr size_t kMaxBodyBytes = 12288;  // feed v2: cards, 6 pictures and messages

portMUX_TYPE g_mux = portMUX_INITIALIZER_UNLOCKED;
WorkshopLocalAiFeedSnapshot g_snap;
char g_address[16] = {};
char g_tlsName[64] = {};
char g_key[56] = {};
char* g_ca = nullptr;  // PSRAM or heap, kMaxCaBytes
std::uint32_t g_generation = 0;
std::uint32_t g_nextAtMs = 0;
bool g_taskActive = false;

// Jobs for the one task, highest priority first.
enum class Job : std::uint8_t { Ask, Decide, Approvals, Image, Feed, Heartbeat, Events };
WorkshopLocalAiExtras g_extras;
char g_askPending[12] = {};
bool g_imagePending = false;
bool g_feedNow = false;               // the long poll saw news
bool g_approvalsPending = false;
char g_decideId[40] = {};
bool g_decideApprove = false;
std::uint32_t g_nextBeatAtMs = 0;
std::uint32_t g_eventsPauseUntilMs = 0;  // after a failed long poll (older Local AI: 404), wait before the next
char g_sig[24] = {};                  // what the long poll compares

// The pictures (feed v2 `images`, or the image card).
struct Picture { char path[lai::kImagePathLen]; char title[lai::kTextLen]; std::uint32_t at; };
Picture g_pictures[lai::kMaxImages];
char g_imageWant[lai::kImagePathLen] = {};    // the one the UI asked for
char g_imageLoaded[lai::kImagePathLen] = {};  // the one in g_image (not downloaded again)
std::uint8_t* g_image = nullptr;   // PSRAM, kMaxImageBytes
std::size_t g_imageLen = 0;

// Messages waiting for the UI, oldest first.
lai::Message g_messages[lai::kMaxMessages];
std::uint8_t g_messageCount = 0;
std::uint64_t g_lastSeq = 0;  // the newest message taken from the feed

lai::Approval g_approvals[lai::kMaxApprovals];

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

// The long poll gives way to anything the person is waiting for.
bool somethingWaits() {
    portENTER_CRITICAL(&g_mux);
    const bool waits = g_askPending[0] || g_imagePending || g_approvalsPending || g_decideId[0];
    portEXIT_CRITICAL(&g_mux);
    return waits;
}

// One HTTP/1.0 request, so the answer is a plain body until the connection closes (HTTP/1.1 comes back chunked through
// Caddy). Sends it with the display key (and `body`, as JSON, for a POST) and reads the status line and headers; on
// HTTP 200 the body is next on `client`. False with `error` set otherwise (the connection is closed then). It waits up
// to `waitMs` for the answer to start, and (when `yieldToPerson`) stops waiting when someone asks for something.
bool openRequest(WiFiClientSecure& client, const char* method, const char* path, const char* accept, const char* body,
                 size_t& contentLength, char* contentType, size_t contentTypeLen, char* error, size_t errorLen,
                 std::uint32_t waitMs = 8000UL, bool yieldToPerson = false) {
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
    const size_t bodyLen = body ? strlen(body) : 0;
    client.printf("%s %s HTTP/1.0\r\nHost: %s\r\nUser-Agent: Workshop-Display/12 ESP32HTTPClient\r\n"
                  "Accept: %s\r\nX-LocalAI-Display-Key: %s\r\nConnection: close\r\n", method, path, name, accept, key);
    memset(key, 0, sizeof(key));
    if (body) client.printf("Content-Type: application/json\r\nContent-Length: %u\r\n\r\n%s", (unsigned)bodyLen, body);
    else client.print("\r\n");

    // Wait for the first bytes of the answer (Stream reads give up after 1 s; Local AI may take longer to start).
    const std::uint32_t sentAt = millis();
    while (!client.available() && client.connected() && millis() - sentAt < waitMs) {
        if (yieldToPerson && somethingWaits()) { client.stop(); copyText(error, errorLen, "gave way"); return false; }
        delay(10);
    }
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

bool openGet(WiFiClientSecure& client, const char* path, const char* accept, size_t& contentLength, char* contentType,
             size_t contentTypeLen, char* error, size_t errorLen) {
    return openRequest(client, "GET", path, accept, nullptr, contentLength, contentType, contentTypeLen, error, errorLen);
}

// A small JSON answer into `doc`.
bool getJson(const char* method, const char* path, const char* body, JsonDocument& doc, char* error, size_t errorLen,
             std::uint32_t waitMs = 8000UL, bool yieldToPerson = false) {
    WiFiClientSecure client;
    size_t contentLength = 0;
    if (!openRequest(client, method, path, "application/json", body, contentLength, nullptr, 0, error, errorLen, waitMs, yieldToPerson)) return false;
    if (contentLength > kMaxBodyBytes) { copyText(error, errorLen, "Local AI's answer was too large."); client.stop(); return false; }
    const DeserializationError err = deserializeJson(doc, client);
    client.stop();
    if (err) { copyText(error, errorLen, "Local AI's answer was not valid JSON."); return false; }
    return true;
}

struct FeedResult {
    Card cards[lai::kMaxCards];
    std::uint8_t count;
    Picture pictures[lai::kMaxImages];
    std::uint8_t pictureCount;
    lai::Message messages[lai::kMaxMessages];
    std::uint8_t messageCount;
    std::uint64_t newestSeq;
};

bool fetch(FeedResult& r, char* error, size_t errorLen) {
    memset(&r, 0, sizeof(r));
    JsonDocument doc;
    if (!getJson("GET", "/api/display/feed", nullptr, doc, error, errorLen)) return false;
    Picture fromCard{};
    for (JsonObject c : doc["cards"].as<JsonArray>()) {
        const char* kind = c["kind"] | "";
        if (!strcmp(kind, "image")) {
            if (!fromCard.path[0] && lai::validImagePath(c["imageUrl"] | "")) {
                copyText(fromCard.path, sizeof(fromCard.path), c["imageUrl"] | "");
                copyText(fromCard.title, sizeof(fromCard.title), c["text"] | "");
                fromCard.at = c["at"] | 0U;
            }
            continue;
        }
        if (!lai::shownKind(kind) || r.count >= lai::kMaxCards) continue;
        Card& out = r.cards[r.count++];
        copyText(out.kind, sizeof(out.kind), kind);
        copyText(out.title, sizeof(out.title), c["title"] | "");
        copyText(out.text, sizeof(out.text), c["text"] | "");
        copyText(out.id, sizeof(out.id), c["id"] | "");
        copyText(out.ask, sizeof(out.ask), c["ask"] | "");
        out.at = c["at"] | 0U;
        out.tone = lai::toneFrom(c["tone"] | "");
    }
    // The gallery (feed v2), else the image card alone (Local AI before v2).
    for (JsonObject i : doc["images"].as<JsonArray>()) {
        if (r.pictureCount >= lai::kMaxImages || !lai::validImagePath(i["imageUrl"] | "")) continue;
        Picture& p = r.pictures[r.pictureCount++];
        copyText(p.path, sizeof(p.path), i["imageUrl"] | "");
        copyText(p.title, sizeof(p.title), i["title"] | "");
        p.at = i["at"] | 0U;
    }
    if (!r.pictureCount && fromCard.path[0]) r.pictures[r.pictureCount++] = fromCard;
    // Messages newer than the last one taken (just after a restart, only the last 2 minutes').
    const time_t now = time(nullptr);
    const std::uint32_t nowEpoch = now >= 1700000000 ? (std::uint32_t)now : 0U;
    portENTER_CRITICAL(&g_mux);
    const std::uint64_t lastSeq = g_lastSeq;
    portEXIT_CRITICAL(&g_mux);
    r.newestSeq = lastSeq;
    for (JsonObject m : doc["messages"].as<JsonArray>()) {
        const std::uint64_t seq = m["seq"] | (std::uint64_t)0;
        if (seq > r.newestSeq) r.newestSeq = seq;
        if (!lai::messageIsNew(seq, lastSeq, m["at"] | 0U, nowEpoch) || r.messageCount >= lai::kMaxMessages) continue;
        lai::Message& out = r.messages[r.messageCount++];
        out.seq = seq;
        copyText(out.title, sizeof(out.title), m["title"] | "");
        copyText(out.text, sizeof(out.text), m["text"] | "");
        out.tone = lai::toneFrom(m["tone"] | "");
        out.chime = m["chime"] | false;
        const char* type = m["action"]["type"] | "";
        if (!strcmp(type, "timer")) {
            const int minutes = m["action"]["minutes"] | 0;
            if (minutes >= 1 && minutes <= 240) { out.action = lai::Action::Timer; out.minutes = (std::uint16_t)minutes; }
        } else if (!strcmp(type, "show") && lai::validPage(m["action"]["page"] | "")) {
            out.action = lai::Action::Show;
            copyText(out.page, sizeof(out.page), m["action"]["page"] | "");
        }
    }
    // After a restart, the first feed sets where "new" starts: its newest message, or (with none) any later one.
    if (!r.newestSeq) r.newestSeq = 1;
    return true;
}

bool ask(const char* question, char* answer, size_t answerLen) {
    char path[48];
    snprintf(path, sizeof(path), "/api/display/ask?q=%s", question);
    JsonDocument doc;
    if (!getJson("GET", path, nullptr, doc, answer, answerLen)) return false;
    const char* text = doc["answer"] | "";
    if (!text[0]) { copyText(answer, answerLen, "Local AI's answer was not valid."); return false; }
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

void finishJob() {
    g_taskActive = false;  // with g_mux held
}

void runAsk() {
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
    finishJob();
    portEXIT_CRITICAL(&g_mux);
}

void runImage() {
    char path[lai::kImagePathLen], error[96] = {};
    portENTER_CRITICAL(&g_mux);
    copyText(path, sizeof(path), g_imageWant);
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
    finishJob();
    portEXIT_CRITICAL(&g_mux);
}

// Picks picture `i` of the gallery for the UI (and the download), with g_mux held.
void selectPictureLocked(std::uint8_t i) {
    if (i >= g_extras.imageCount) i = 0;
    g_extras.imageIndex = i;
    const Picture& p = g_pictures[i];
    copyText(g_imageWant, sizeof(g_imageWant), p.path);
    copyText(g_extras.imageText, sizeof(g_extras.imageText), p.title);
    g_extras.imageAt = p.at;
}

void runFeed(std::uint32_t generation) {
    static FeedResult r;
    char error[96] = {};
    const bool ok = fetch(r, error, sizeof(error));
    const std::uint32_t now = millis();
    portENTER_CRITICAL(&g_mux);
    if (generation == g_generation) {  // never publish cards fetched under settings that changed meanwhile
        g_snap.lastAttemptAtMs = now;
        if (ok) {
            memcpy(g_snap.cards, r.cards, sizeof(r.cards));
            g_snap.count = r.count;
            g_snap.lastSuccessAtMs = now;
            g_snap.failures = 0;
            copyText(g_snap.status, sizeof(g_snap.status), "Local AI cards are current.");
            // The gallery: keep showing the picture the UI is on when it is still there.
            char current[lai::kImagePathLen];
            copyText(current, sizeof(current), g_imageWant);
            memcpy(g_pictures, r.pictures, sizeof(r.pictures));
            g_extras.imageCount = r.pictureCount;
            g_extras.hasImage = r.pictureCount > 0;
            std::uint8_t keep = 0;
            for (std::uint8_t i = 0; i < r.pictureCount; ++i)
                if (!strcmp(g_pictures[i].path, current)) keep = i;
            if (r.pictureCount) selectPictureLocked(g_extras.imageBusy ? g_extras.imageIndex : keep);
            // A new newest picture is fetched now, in the background, so opening it is instant.
            if (r.pictureCount && !g_extras.imageBusy && strcmp(g_imageWant, g_imageLoaded) != 0 && g_extras.imageIndex == 0) {
                g_imagePending = true;
                g_extras.imageBusy = true;
                g_extras.imageStatus[0] = 0;
            }
            for (std::uint8_t i = 0; i < r.messageCount; ++i) {
                if (g_messageCount == lai::kMaxMessages) {  // the oldest gives way
                    memmove(&g_messages[0], &g_messages[1], sizeof(g_messages[0]) * (lai::kMaxMessages - 1));
                    --g_messageCount;
                }
                g_messages[g_messageCount++] = r.messages[i];
            }
            if (r.newestSeq > g_lastSeq) g_lastSeq = r.newestSeq;
        } else {
            if (g_snap.failures < 8) ++g_snap.failures;
            copyText(g_snap.status, sizeof(g_snap.status), error);
        }
        g_nextAtMs = now + lai::nextDelayMs(g_snap.failures);
    }
    g_snap.busy = false;
    finishJob();
    portEXIT_CRITICAL(&g_mux);
}

void runApprovals() {
    portENTER_CRITICAL(&g_mux);
    g_approvalsPending = false;
    portEXIT_CRITICAL(&g_mux);
    JsonDocument doc;
    char error[96] = {};
    const bool ok = getJson("GET", "/api/display/approvals", nullptr, doc, error, sizeof(error));
    lai::Approval list[lai::kMaxApprovals];
    std::uint8_t n = 0, total = 0;
    if (ok) {
        for (JsonObject a : doc["items"].as<JsonArray>()) {
            ++total;
            if (n >= lai::kMaxApprovals) continue;
            lai::Approval& out = list[n++];
            copyText(out.id, sizeof(out.id), a["id"] | "");
            copyText(out.title, sizeof(out.title), a["title"] | "");
            copyText(out.risk, sizeof(out.risk), a["risk"] | "");
            out.decidable = a["decidable"] | false;
        }
    }
    portENTER_CRITICAL(&g_mux);
    if (ok) {
        memcpy(g_approvals, list, sizeof(list[0]) * n);
        g_extras.approvalCount = n;
        g_extras.approvalTotal = total;
        g_extras.approvalStatus[0] = 0;
    } else {
        copyText(g_extras.approvalStatus, sizeof(g_extras.approvalStatus), error);
    }
    g_extras.approvalsBusy = false;
    ++g_extras.approvalSeq;
    finishJob();
    portEXIT_CRITICAL(&g_mux);
}

void runDecide() {
    char id[40], body[96], error[96] = {};
    bool approve;
    portENTER_CRITICAL(&g_mux);
    copyText(id, sizeof(id), g_decideId);
    approve = g_decideApprove;
    g_decideId[0] = 0;
    portEXIT_CRITICAL(&g_mux);
    JsonDocument idDoc;
    idDoc["id"] = id;
    idDoc["decision"] = approve ? "approved" : "rejected";
    serializeJson(idDoc, body, sizeof(body));
    JsonDocument doc;
    const bool ok = getJson("POST", "/api/display/approvals/decide", body, doc, error, sizeof(error));
    portENTER_CRITICAL(&g_mux);
    if (ok) snprintf(g_extras.approvalStatus, sizeof(g_extras.approvalStatus), approve ? "Approved." : "Rejected.");
    else copyText(g_extras.approvalStatus, sizeof(g_extras.approvalStatus), error);
    g_approvalsPending = true;  // and read the list again
    g_extras.approvalsBusy = true;
    finishJob();
    portEXIT_CRITICAL(&g_mux);
}

void runHeartbeat() {
    JsonDocument beat;
    beat["version"] = WORKSHOP_OS_RELEASE_VERSION;
    beat["sourceSha"] = WORKSHOP_OS_SOURCE_SHA;
    beat["uptimeS"] = millis() / 1000UL;
    beat["rssi"] = WiFi.RSSI();
    beat["heapFree"] = ESP.getFreeHeap();
    beat["psramFree"] = ESP.getFreePsram();
    char body[256];
    serializeJson(beat, body, sizeof(body));
    JsonDocument doc;
    char error[96] = {};
    getJson("POST", "/api/display/heartbeat", body, doc, error, sizeof(error));  // best effort
    portENTER_CRITICAL(&g_mux);
    g_nextBeatAtMs = millis() + lai::kHeartbeatMs;
    finishJob();
    portEXIT_CRITICAL(&g_mux);
}

void runEvents() {
    char path[64], error[96] = {};
    portENTER_CRITICAL(&g_mux);
    snprintf(path, sizeof(path), "/api/display/events?since=%s", g_sig[0] ? g_sig : "none");
    portEXIT_CRITICAL(&g_mux);
    JsonDocument doc;
    const bool ok = getJson("GET", path, nullptr, doc, error, sizeof(error), lai::kEventsHoldMs, true);
    portENTER_CRITICAL(&g_mux);
    if (ok) {
        const char* sig = doc["sig"] | "";
        if (doc["changed"] | false) g_feedNow = true;  // news: fetch the feed now
        copyText(g_sig, sizeof(g_sig), sig);
        g_extras.live = true;
    } else if (strcmp(error, "gave way") != 0) {
        g_eventsPauseUntilMs = millis() + 60000UL;  // Local AI without the long poll, or away: the minute poll goes on
        g_extras.live = false;
    }
    finishJob();
    portEXIT_CRITICAL(&g_mux);
}

void fetchTask(void* arg) {
    const Job job = static_cast<Job>(reinterpret_cast<std::uintptr_t>(arg));
    portENTER_CRITICAL(&g_mux);
    const std::uint32_t generation = g_generation;
    portEXIT_CRITICAL(&g_mux);
    switch (job) {
        case Job::Ask: runAsk(); break;
        case Job::Decide: runDecide(); break;
        case Job::Approvals: runApprovals(); break;
        case Job::Image: runImage(); break;
        case Job::Feed: runFeed(generation); break;
        case Job::Heartbeat: runHeartbeat(); break;
        case Job::Events: runEvents(); break;
    }
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
    g_nextBeatAtMs = millis() + 60000UL;
    portEXIT_CRITICAL(&g_mux);
}

void workshopLocalAiFeedLoop() {
    const std::uint32_t now = millis();
    Job job = Job::Feed;
    bool due = false;
    portENTER_CRITICAL(&g_mux);
    if (g_snap.configured && !g_taskActive) {
        due = true;
        if (g_askPending[0]) job = Job::Ask;
        else if (g_decideId[0]) job = Job::Decide;
        else if (g_approvalsPending) job = Job::Approvals;
        else if (g_imagePending) job = Job::Image;
        else if (g_feedNow || (std::int32_t)(now - g_nextAtMs) >= 0) { job = Job::Feed; g_feedNow = false; g_snap.busy = true; }
        else if ((std::int32_t)(now - g_nextBeatAtMs) >= 0) job = Job::Heartbeat;
        else if (g_snap.lastSuccessAtMs && (std::int32_t)(now - g_eventsPauseUntilMs) >= 0) job = Job::Events;
        else due = false;
    }
    if (due) g_taskActive = true;
    portEXIT_CRITICAL(&g_mux);
    if (!due) return;
    if (xTaskCreatePinnedToCore(fetchTask, "ws12LocalAi", 12288, reinterpret_cast<void*>(static_cast<std::uintptr_t>(job)), 1, nullptr, 0) != pdPASS) {
        portENTER_CRITICAL(&g_mux);
        g_taskActive = false;
        switch (job) {
            case Job::Feed: g_snap.busy = false; g_nextAtMs = now + lai::kPollMs; break;
            case Job::Ask: g_askPending[0] = 0; g_extras.askBusy = false; g_extras.askOk = false; copyText(g_extras.askAnswer, sizeof(g_extras.askAnswer), "Could not start the request."); ++g_extras.askSeq; break;
            case Job::Image: g_imagePending = false; g_extras.imageBusy = false; copyText(g_extras.imageStatus, sizeof(g_extras.imageStatus), "Could not start the download."); ++g_extras.imageSeq; break;
            case Job::Approvals: g_approvalsPending = false; g_extras.approvalsBusy = false; break;
            case Job::Decide: g_decideId[0] = 0; break;
            case Job::Heartbeat: g_nextBeatAtMs = now + lai::kHeartbeatMs; break;
            case Job::Events: g_eventsPauseUntilMs = now + 10000UL; break;
        }
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
    g_sig[0] = 0;
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
    g_imageWant[0] = g_imageLoaded[0] = 0;
    g_extras.hasImage = false;
    g_extras.imageReady = false;
    g_extras.imageCount = 0;
    g_extras.approvalCount = g_extras.approvalTotal = 0;
    g_messageCount = 0;
    g_sig[0] = 0;
    g_extras.live = false;
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
    if (g_extras.imageReady && !g_extras.imageBusy && !strcmp(g_imageWant, g_imageLoaded)) {  // already here
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

bool workshopLocalAiFeedShowImage(std::uint8_t index) {
    portENTER_CRITICAL(&g_mux);
    const bool ok = g_extras.imageCount && !g_extras.imageBusy && index < g_extras.imageCount;
    if (ok) selectPictureLocked(index);
    portEXIT_CRITICAL(&g_mux);
    return ok && workshopLocalAiFeedFetchImage();
}

bool workshopLocalAiFeedTakeMessage(workshop::localai::Message* out) {
    portENTER_CRITICAL(&g_mux);
    const bool ok = g_messageCount > 0;
    if (ok) {
        if (out) *out = g_messages[0];
        memmove(&g_messages[0], &g_messages[1], sizeof(g_messages[0]) * (lai::kMaxMessages - 1));
        --g_messageCount;
    }
    portEXIT_CRITICAL(&g_mux);
    return ok;
}

bool workshopLocalAiFeedRefreshApprovals() {
    portENTER_CRITICAL(&g_mux);
    const bool ok = g_snap.configured && !g_extras.approvalsBusy;
    if (ok) { g_approvalsPending = true; g_extras.approvalsBusy = true; g_extras.approvalStatus[0] = 0; }
    portEXIT_CRITICAL(&g_mux);
    return ok;
}

std::uint8_t workshopLocalAiFeedApprovals(workshop::localai::Approval* out, std::uint8_t max) {
    portENTER_CRITICAL(&g_mux);
    std::uint8_t n = g_extras.approvalCount < max ? g_extras.approvalCount : max;
    if (out) memcpy(out, g_approvals, sizeof(g_approvals[0]) * n);
    portEXIT_CRITICAL(&g_mux);
    return n;
}

bool workshopLocalAiFeedDecide(const char* id, bool approve) {
    if (!id || !id[0] || strlen(id) >= sizeof(g_decideId)) return false;
    portENTER_CRITICAL(&g_mux);
    bool decidable = false;
    for (std::uint8_t i = 0; i < g_extras.approvalCount; ++i)
        if (!strcmp(g_approvals[i].id, id)) decidable = g_approvals[i].decidable;
    const bool ok = g_snap.configured && decidable && !g_decideId[0] && !g_extras.approvalsBusy;
    if (ok) {
        copyText(g_decideId, sizeof(g_decideId), id);
        g_decideApprove = approve;
        g_extras.approvalsBusy = true;
        snprintf(g_extras.approvalStatus, sizeof(g_extras.approvalStatus), approve ? "Approving..." : "Rejecting...");
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
    const bool ok = g_extras.imageReady && !g_extras.imageBusy && g_image && g_imageLen && !strcmp(g_imageWant, g_imageLoaded);
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
