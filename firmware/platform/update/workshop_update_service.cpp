#include "workshop_update_service.h"

#include "bambu_mqtt.h"
#include "smart_home_build.h"
#include "wifi_manager.h"
#include "workshop_platform_bridge.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <esp_ota_ops.h>
#include <mbedtls/sha256.h>

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <cstring>

#ifndef WORKSHOP_OS12_SOURCE_SHA
#define WORKSHOP_OS12_SOURCE_SHA "unknown"
#endif

namespace {
using workshop::platform::Freshness;
using workshop::platform::PrinterActivity;
using workshop::platform::UpdateChannel;
using workshop::platform::UpdatePhase;
using workshop::platform::UpdateState;

constexpr char kManifestUrl[] =
    "https://raw.githubusercontent.com/azmusgb/bambuhelper-smart-display/main/releases/device-update.json";
constexpr char kAuthority[] = "azmusgb/bambuhelper-smart-display";
constexpr char kBoard[] = "ws_lcd_350";
constexpr char kArtifactBaseUrl[] =
    "https://raw.githubusercontent.com/azmusgb/bambuhelper-smart-display/main/";
constexpr std::uint32_t kManifestMaxBytes = 24U * 1024U;
constexpr std::uint32_t kDownloadNoProgressTimeoutMs = 20000U;
constexpr std::uint32_t kRebootDelayMs = 4000U;
constexpr std::size_t kDownloadBufferBytes = 4096U;

#if defined(BOARD_IS_WS350) && defined(ENABLE_OTA_AUTO)
constexpr bool kOtaSupported = true;
extern const std::uint8_t rootca_crt_bundle_start[] asm("_binary_x509_crt_bundle_start");
#else
constexpr bool kOtaSupported = false;
#endif

struct CandidateMetadata {
    bool valid{false};
    UpdateChannel channel{UpdateChannel::Stable};
    char version[workshop::platform::kVersionLabelLength]{};
    char label[80]{};
    char sourceCommit[41]{};
    char path[224]{};
    char sha256[65]{};
    std::uint32_t size{0};
};

enum class PendingOperation : std::uint8_t {
    None = 0,
    Check,
    Install,
};

portMUX_TYPE g_updateMux = portMUX_INITIALIZER_UNLOCKED;
WorkshopUpdateRuntimeSnapshot g_runtime;
CandidateMetadata g_candidate;
PendingOperation g_pendingOperation = PendingOperation::None;
bool g_taskActive = false;
bool g_mqttReinitPending = false;
std::uint32_t g_internalRevision = 0;
std::uint32_t g_publishedRevision = 0;

void copyText(char* dst, std::size_t len, const char* src) {
    if (!dst || len == 0) return;
    if (!src) src = "";
    strlcpy(dst, src, len);
}

void bumpRevisionLocked() {
    ++g_internalRevision;
    if (g_internalRevision == 0) ++g_internalRevision;
}

void clearCandidateLocked() {
    g_candidate = CandidateMetadata{};
    g_runtime.updateAvailable = false;
    g_runtime.artifactIdentityVerified = false;
    g_runtime.availableVersion[0] = '\0';
    g_runtime.availableLabel[0] = '\0';
    g_runtime.sourceCommit[0] = '\0';
    g_runtime.artifactSha256[0] = '\0';
    g_runtime.artifactSize = 0;
}

void setRuntimeState(UpdatePhase phase,
                     std::uint8_t progress,
                     bool busy,
                     const char* message) {
    portENTER_CRITICAL(&g_updateMux);
    g_runtime.phase = phase;
    g_runtime.progressPercent = progress > 100U ? 100U : progress;
    g_runtime.busy = busy;
    copyText(g_runtime.statusMessage, sizeof(g_runtime.statusMessage), message);
    bumpRevisionLocked();
    portEXIT_CRITICAL(&g_updateMux);
}

void setRuntimeFailure(const char* message, bool preserveCandidate) {
    portENTER_CRITICAL(&g_updateMux);
    if (!preserveCandidate) clearCandidateLocked();
    g_runtime.phase = UpdatePhase::Failed;
    g_runtime.progressPercent = 0;
    g_runtime.busy = false;
    g_runtime.manifestFreshness = Freshness::Stale;
    copyText(g_runtime.statusMessage, sizeof(g_runtime.statusMessage), message);
    bumpRevisionLocked();
    portEXIT_CRITICAL(&g_updateMux);
}

void markMqttReinitPending() {
    portENTER_CRITICAL(&g_updateMux);
    g_mqttReinitPending = true;
    portEXIT_CRITICAL(&g_updateMux);
}

bool isHexString(const char* value, std::size_t exactLength) {
    if (!value || std::strlen(value) != exactLength) return false;
    for (std::size_t i = 0; i < exactLength; ++i) {
        if (!std::isxdigit(static_cast<unsigned char>(value[i]))) return false;
    }
    return true;
}

bool safeArtifactPath(const char* path) {
    if (!path) return false;
    const std::size_t len = std::strlen(path);
    if (len == 0 || len >= sizeof(CandidateMetadata::path)) return false;
    if (path[0] == '/' || std::strstr(path, "..") || std::strstr(path, "://") || std::strchr(path, '\\')) {
        return false;
    }
    return std::strncmp(path, "firmware/", 9) == 0 ||
           std::strncmp(path, "releases/", 9) == 0;
}

bool parseVersionCore(const char* raw, std::uint32_t parts[3]) {
    if (!raw || !*raw) return false;
    const char* p = raw;
    if (*p == 'v' || *p == 'V') ++p;
    for (int i = 0; i < 3; ++i) parts[i] = 0;

    int index = 0;
    bool sawDigit = false;
    while (*p && *p != '-' && *p != '+') {
        if (*p == '.') {
            if (!sawDigit || index >= 2) return false;
            ++index;
            sawDigit = false;
            ++p;
            continue;
        }
        if (*p < '0' || *p > '9') return false;
        sawDigit = true;
        const std::uint32_t digit = static_cast<std::uint32_t>(*p - '0');
        if (parts[index] > 1000000U) return false;
        parts[index] = parts[index] * 10U + digit;
        ++p;
    }
    return sawDigit;
}

int compareVersions(const char* candidate, const char* running) {
    std::uint32_t c[3] = {}, r[3] = {};
    if (!parseVersionCore(candidate, c) || !parseVersionCore(running, r)) return -2;
    for (int i = 0; i < 3; ++i) {
        if (c[i] > r[i]) return 1;
        if (c[i] < r[i]) return -1;
    }
    return 0;
}

const char* channelKey(UpdateChannel channel) {
    return channel == UpdateChannel::Candidate ? "candidate" : "stable";
}

bool printerUpdateGuardSatisfied(char* reason, std::size_t reasonLen) {
    const workshop::platform::WorkshopState& state = workshopPlatformState();
    for (std::size_t slot = 0; slot < workshop::platform::kMaxPrinterSlots; ++slot) {
        const auto& printer = state.printers[slot];
        if (!printer.configured) continue;
        if (workshop::platform::printerActivityIsActive(printer.activity)) {
            copyText(reason, reasonLen, "Finish or stop the active print before updating Workshop OS.");
            return false;
        }
    }
    return true;
}

void publishRuntimeToPlatform(const WorkshopUpdateRuntimeSnapshot& snap) {
    UpdateState state;
    state.channel = snap.channel;
    state.phase = snap.phase;
    state.manifestFreshness = snap.manifestFreshness;
    copyText(state.runningVersion, sizeof(state.runningVersion), snap.runningVersion);
    copyText(state.availableVersion, sizeof(state.availableVersion), snap.availableVersion);
    state.otaSupported = kOtaSupported;
    state.recoveryFullImageSupported = false;
    state.artifactIdentityVerified = snap.artifactIdentityVerified;
    state.rollbackAvailable = false;
    workshopPlatformPublishUpdateState(state);
}

#if defined(BOARD_IS_WS350) && defined(ENABLE_OTA_AUTO)
bool beginHttps(HTTPClient& http, WiFiClientSecure& client, const char* url) {
    client.setCACertBundle(rootca_crt_bundle_start);
    http.setTimeout(15000);
    http.setConnectTimeout(10000);
    http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);
    http.setUserAgent("WorkshopOS-WS350/12");
    return http.begin(client, url);
}

bool fetchManifest(CandidateMetadata& out, String& error) {
    if (WiFi.status() != WL_CONNECTED || isAPMode()) {
        error = "Internet connection required to check GitHub for updates.";
        return false;
    }

    WiFiClientSecure client;
    HTTPClient http;
    if (!beginHttps(http, client, kManifestUrl)) {
        error = "Could not initialize the GitHub manifest request.";
        return false;
    }

    const int code = http.GET();
    if (code != HTTP_CODE_OK) {
        error = String("GitHub manifest request failed (HTTP ") + code + ").";
        http.end();
        return false;
    }
    const int contentLength = http.getSize();
    if (contentLength <= 0 || static_cast<std::uint32_t>(contentLength) > kManifestMaxBytes) {
        error = "GitHub manifest size is missing or outside the accepted limit.";
        http.end();
        return false;
    }

    JsonDocument doc;
    const DeserializationError jsonError = deserializeJson(doc, http.getStream());
    http.end();
    if (jsonError) {
        error = String("GitHub manifest JSON is invalid: ") + jsonError.c_str();
        return false;
    }

    if ((doc["schemaVersion"] | 0) != 1) {
        error = "Unsupported device-update manifest schema.";
        return false;
    }
    const char* board = doc["board"] | "";
    const char* authority = doc["authority"] | "";
    const char* artifactBase = doc["artifactBaseUrl"] | "";
    if (std::strcmp(board, kBoard) != 0 ||
        std::strcmp(authority, kAuthority) != 0 ||
        std::strcmp(artifactBase, kArtifactBaseUrl) != 0) {
        error = "GitHub manifest authority, board, or artifact base does not match Workshop OS policy.";
        return false;
    }

    const WorkshopUpdateRuntimeSnapshot snap = workshopUpdateSnapshot();
    JsonObject channel = doc["channels"][channelKey(snap.channel)].as<JsonObject>();
    if (channel.isNull()) {
        error = "Selected update channel is missing from the GitHub manifest.";
        return false;
    }
    const char* status = channel["status"] | "";
    if (std::strcmp(status, "published") != 0) {
        error = "No published update is available on the selected channel.";
        return false;
    }

    JsonObject ota = channel["ota"].as<JsonObject>();
    if (ota.isNull()) {
        error = "Published channel does not contain an OTA application image.";
        return false;
    }

    const char* version = channel["version"] | "";
    const char* label = channel["label"] | "";
    const char* sourceCommit = channel["sourceCommit"] | "";
    const char* path = ota["path"] | "";
    const char* sha256 = ota["sha256"] | "";
    const unsigned long size = ota["size"] | 0UL;

    if (!parseVersionCore(version, (std::uint32_t[3]){0, 0, 0})) {
        // C++ does not permit retaining the temporary array beyond this call;
        // this branch exists only to keep the validation expression explicit.
    }

    std::uint32_t parsedVersion[3] = {};
    if (!parseVersionCore(version, parsedVersion)) {
        error = "Published update version is malformed.";
        return false;
    }
    if (!safeArtifactPath(path) || !isHexString(sha256, 64) ||
        !isHexString(sourceCommit, 40) || size == 0) {
        error = "Published OTA identity is incomplete or invalid.";
        return false;
    }

    const esp_partition_t* next = esp_ota_get_next_update_partition(nullptr);
    if (!next || size > next->size) {
        error = "Published OTA image does not fit the inactive application partition.";
        return false;
    }

    const int comparison = compareVersions(version, SMART_HOME_VERSION);
    if (comparison == -2) {
        error = "Running Workshop OS version cannot be compared safely.";
        return false;
    }
    if (comparison <= 0) {
        portENTER_CRITICAL(&g_updateMux);
        clearCandidateLocked();
        g_runtime.phase = UpdatePhase::Idle;
        g_runtime.progressPercent = 0;
        g_runtime.busy = false;
        g_runtime.manifestFreshness = Freshness::Fresh;
        copyText(g_runtime.statusMessage, sizeof(g_runtime.statusMessage), "Workshop OS is up to date on this channel.");
        bumpRevisionLocked();
        portEXIT_CRITICAL(&g_updateMux);
        return true;
    }

    out = CandidateMetadata{};
    out.valid = true;
    out.channel = snap.channel;
    copyText(out.version, sizeof(out.version), version);
    copyText(out.label, sizeof(out.label), label);
    copyText(out.sourceCommit, sizeof(out.sourceCommit), sourceCommit);
    copyText(out.path, sizeof(out.path), path);
    copyText(out.sha256, sizeof(out.sha256), sha256);
    out.size = static_cast<std::uint32_t>(size);
    return true;
}

bool hexToBytes(const char* hex, std::uint8_t out[32]) {
    if (!isHexString(hex, 64)) return false;
    for (std::size_t i = 0; i < 32; ++i) {
        auto nibble = [](char c) -> int {
            if (c >= '0' && c <= '9') return c - '0';
            if (c >= 'a' && c <= 'f') return c - 'a' + 10;
            if (c >= 'A' && c <= 'F') return c - 'A' + 10;
            return -1;
        };
        const int hi = nibble(hex[i * 2]);
        const int lo = nibble(hex[i * 2 + 1]);
        if (hi < 0 || lo < 0) return false;
        out[i] = static_cast<std::uint8_t>((hi << 4) | lo);
    }
    return true;
}

bool downloadAndStage(const CandidateMetadata& meta, String& error) {
    if (!meta.valid || meta.size == 0 || !safeArtifactPath(meta.path)) {
        error = "Cached OTA identity is not installable.";
        return false;
    }
    if (WiFi.status() != WL_CONNECTED || isAPMode()) {
        error = "Internet connection was lost before the OTA download started.";
        return false;
    }

    char url[sizeof(kArtifactBaseUrl) + sizeof(meta.path) + 8] = {};
    snprintf(url, sizeof(url), "%s%s", kArtifactBaseUrl, meta.path);

    WiFiClientSecure client;
    HTTPClient http;
    if (!beginHttps(http, client, url)) {
        error = "Could not initialize the OTA download.";
        return false;
    }
    const int code = http.GET();
    if (code != HTTP_CODE_OK) {
        error = String("OTA download failed (HTTP ") + code + ").";
        http.end();
        return false;
    }

    const int declaredLength = http.getSize();
    if (declaredLength <= 0 || static_cast<std::uint32_t>(declaredLength) != meta.size) {
        error = "OTA Content-Length does not match the signed manifest size.";
        http.end();
        return false;
    }

    const esp_partition_t* next = esp_ota_get_next_update_partition(nullptr);
    if (!next || meta.size > next->size) {
        error = "OTA image does not fit the inactive application partition.";
        http.end();
        return false;
    }

    esp_ota_handle_t otaHandle = 0;
    esp_err_t otaResult = esp_ota_begin(next, meta.size, &otaHandle);
    if (otaResult != ESP_OK) {
        error = String("Could not open inactive OTA partition: ") + esp_err_to_name(otaResult);
        http.end();
        return false;
    }
    bool otaOpen = true;

    mbedtls_sha256_context sha;
    mbedtls_sha256_init(&sha);
    if (mbedtls_sha256_starts_ret(&sha, 0) != 0) {
        error = "Could not initialize OTA SHA-256 verification.";
        esp_ota_abort(otaHandle);
        http.end();
        mbedtls_sha256_free(&sha);
        return false;
    }

    std::uint8_t buffer[kDownloadBufferBytes];
    std::uint32_t received = 0;
    std::uint8_t lastProgress = 0;
    std::uint32_t lastDataAt = millis();
    WiFiClient* stream = http.getStreamPtr();

    while (received < meta.size) {
        const int available = stream ? stream->available() : 0;
        if (available > 0) {
            const std::size_t remaining = static_cast<std::size_t>(meta.size - received);
            const std::size_t want = std::min<std::size_t>(
                std::min<std::size_t>(static_cast<std::size_t>(available), sizeof(buffer)), remaining);
            const std::size_t got = stream->readBytes(reinterpret_cast<char*>(buffer), want);
            if (got == 0) {
                error = "OTA download stopped while reading the artifact.";
                break;
            }
            lastDataAt = millis();
            if (mbedtls_sha256_update_ret(&sha, buffer, got) != 0) {
                error = "OTA SHA-256 calculation failed during download.";
                break;
            }
            otaResult = esp_ota_write(otaHandle, buffer, got);
            if (otaResult != ESP_OK) {
                error = String("Writing the inactive OTA partition failed: ") + esp_err_to_name(otaResult);
                break;
            }
            received += static_cast<std::uint32_t>(got);
            const std::uint8_t progress = static_cast<std::uint8_t>((received * 100ULL) / meta.size);
            if (progress != lastProgress) {
                lastProgress = progress;
                setRuntimeState(UpdatePhase::Downloading, progress, true, "Downloading verified GitHub OTA image…");
            }
            continue;
        }

        if (!http.connected()) {
            error = "GitHub closed the OTA connection before the declared image size was received.";
            break;
        }
        if (static_cast<std::uint32_t>(millis() - lastDataAt) > kDownloadNoProgressTimeoutMs) {
            error = "OTA download timed out without progress.";
            break;
        }
        delay(5);
    }

    if (received != meta.size) {
        if (error.length() == 0) error = "OTA byte count does not match the manifest.";
        if (otaOpen) esp_ota_abort(otaHandle);
        mbedtls_sha256_free(&sha);
        http.end();
        return false;
    }

    setRuntimeState(UpdatePhase::Verifying, 100, true, "Verifying OTA SHA-256 before activation…");
    std::uint8_t actualSha[32] = {};
    std::uint8_t expectedSha[32] = {};
    if (mbedtls_sha256_finish_ret(&sha, actualSha) != 0 || !hexToBytes(meta.sha256, expectedSha)) {
        error = "Could not finalize OTA artifact identity verification.";
        esp_ota_abort(otaHandle);
        mbedtls_sha256_free(&sha);
        http.end();
        return false;
    }
    mbedtls_sha256_free(&sha);

    if (std::memcmp(actualSha, expectedSha, sizeof(actualSha)) != 0) {
        error = "OTA SHA-256 does not match the GitHub manifest. Inactive image was rejected.";
        esp_ota_abort(otaHandle);
        http.end();
        return false;
    }

    portENTER_CRITICAL(&g_updateMux);
    g_runtime.artifactIdentityVerified = true;
    g_runtime.phase = UpdatePhase::Staged;
    g_runtime.progressPercent = 100;
    copyText(g_runtime.statusMessage, sizeof(g_runtime.statusMessage), "Artifact identity verified; validating image…");
    bumpRevisionLocked();
    portEXIT_CRITICAL(&g_updateMux);

    otaResult = esp_ota_end(otaHandle);
    otaOpen = false;
    http.end();
    if (otaResult != ESP_OK) {
        error = String("ESP32 rejected the downloaded application image: ") + esp_err_to_name(otaResult);
        return false;
    }

    setRuntimeState(UpdatePhase::Installing, 100, true, "Activating the verified OTA image…");
    otaResult = esp_ota_set_boot_partition(next);
    if (otaResult != ESP_OK) {
        error = String("Verified image could not be selected for the next boot: ") + esp_err_to_name(otaResult);
        return false;
    }

    return true;
}
#endif

void performCheck() {
#if defined(BOARD_IS_WS350) && defined(ENABLE_OTA_AUTO)
    CandidateMetadata discovered;
    String error;
    if (!fetchManifest(discovered, error)) {
        setRuntimeFailure(error.c_str(), false);
        return;
    }
    if (!discovered.valid) {
        // fetchManifest already published the up-to-date state.
        return;
    }

    portENTER_CRITICAL(&g_updateMux);
    g_candidate = discovered;
    g_runtime.phase = UpdatePhase::Available;
    g_runtime.progressPercent = 0;
    g_runtime.busy = false;
    g_runtime.manifestFreshness = Freshness::Fresh;
    g_runtime.updateAvailable = true;
    g_runtime.artifactIdentityVerified = false;
    copyText(g_runtime.availableVersion, sizeof(g_runtime.availableVersion), discovered.version);
    copyText(g_runtime.availableLabel, sizeof(g_runtime.availableLabel), discovered.label);
    copyText(g_runtime.sourceCommit, sizeof(g_runtime.sourceCommit), discovered.sourceCommit);
    copyText(g_runtime.artifactSha256, sizeof(g_runtime.artifactSha256), discovered.sha256);
    g_runtime.artifactSize = discovered.size;
    copyText(g_runtime.statusMessage, sizeof(g_runtime.statusMessage), "A newer GitHub OTA image is available.");
    bumpRevisionLocked();
    portEXIT_CRITICAL(&g_updateMux);
#else
    setRuntimeFailure("Device-native GitHub OTA is supported only on the WS350 target in this OS12 slice.", false);
#endif
}

void performInstall() {
#if defined(BOARD_IS_WS350) && defined(ENABLE_OTA_AUTO)
    CandidateMetadata meta;
    portENTER_CRITICAL(&g_updateMux);
    meta = g_candidate;
    portEXIT_CRITICAL(&g_updateMux);

    String error;
    if (!downloadAndStage(meta, error)) {
        setRuntimeFailure(error.c_str(), true);
        markMqttReinitPending();
        return;
    }

    portENTER_CRITICAL(&g_updateMux);
    g_runtime.phase = UpdatePhase::RebootRequired;
    g_runtime.progressPercent = 100;
    g_runtime.busy = true;
    g_runtime.updateAvailable = false;
    copyText(g_runtime.statusMessage, sizeof(g_runtime.statusMessage), "Verified update installed. Restarting Workshop OS…");
    bumpRevisionLocked();
    portEXIT_CRITICAL(&g_updateMux);

    delay(kRebootDelayMs);
    ESP.restart();
#else
    setRuntimeFailure("Device-native GitHub OTA is unavailable on this target.", true);
#endif
}

void updateTask(void*) {
    PendingOperation operation = PendingOperation::None;
    portENTER_CRITICAL(&g_updateMux);
    operation = g_pendingOperation;
    portEXIT_CRITICAL(&g_updateMux);

    if (operation == PendingOperation::Check) performCheck();
    else if (operation == PendingOperation::Install) performInstall();

    portENTER_CRITICAL(&g_updateMux);
    g_pendingOperation = PendingOperation::None;
    g_taskActive = false;
    if (g_runtime.phase != UpdatePhase::RebootRequired) g_runtime.busy = false;
    bumpRevisionLocked();
    portEXIT_CRITICAL(&g_updateMux);
    vTaskDelete(nullptr);
}

bool startOperation(PendingOperation operation) {
    portENTER_CRITICAL(&g_updateMux);
    if (g_taskActive) {
        portEXIT_CRITICAL(&g_updateMux);
        return false;
    }
    g_taskActive = true;
    g_pendingOperation = operation;
    bumpRevisionLocked();
    portEXIT_CRITICAL(&g_updateMux);

    const BaseType_t created = xTaskCreatePinnedToCore(
        updateTask,
        operation == PendingOperation::Install ? "ws12OtaInstall" : "ws12OtaCheck",
        12288,
        nullptr,
        4,
        nullptr,
        1);
    if (created != pdPASS) {
        portENTER_CRITICAL(&g_updateMux);
        g_taskActive = false;
        g_pendingOperation = PendingOperation::None;
        g_runtime.phase = UpdatePhase::Failed;
        g_runtime.busy = false;
        copyText(g_runtime.statusMessage, sizeof(g_runtime.statusMessage), "Could not start the update worker task.");
        bumpRevisionLocked();
        portEXIT_CRITICAL(&g_updateMux);
        return false;
    }
    return true;
}

}  // namespace

void workshopUpdateServiceBegin() {
    portENTER_CRITICAL(&g_updateMux);
    g_runtime = WorkshopUpdateRuntimeSnapshot{};
    g_candidate = CandidateMetadata{};
    g_runtime.channel = UpdateChannel::Stable;
    g_runtime.phase = UpdatePhase::Idle;
    g_runtime.manifestFreshness = Freshness::Unknown;
    g_runtime.progressPercent = 0;
    g_runtime.busy = false;
    g_runtime.updateAvailable = false;
    g_runtime.artifactIdentityVerified = false;
    copyText(g_runtime.runningVersion, sizeof(g_runtime.runningVersion), SMART_HOME_VERSION);
    copyText(g_runtime.statusMessage,
             sizeof(g_runtime.statusMessage),
             kOtaSupported ? "Ready to check GitHub for Workshop OS updates." :
                             "Device-native GitHub OTA is unavailable on this target.");
    g_taskActive = false;
    g_pendingOperation = PendingOperation::None;
    g_mqttReinitPending = false;
    bumpRevisionLocked();
    portEXIT_CRITICAL(&g_updateMux);
}

void workshopUpdateServiceLoop() {
    WorkshopUpdateRuntimeSnapshot snapshot;
    std::uint32_t revision = 0;
    bool reinitMqtt = false;

    portENTER_CRITICAL(&g_updateMux);
    snapshot = g_runtime;
    revision = g_internalRevision;
    if (g_mqttReinitPending && !g_taskActive) {
        g_mqttReinitPending = false;
        reinitMqtt = true;
    }
    portEXIT_CRITICAL(&g_updateMux);

    if (revision != g_publishedRevision) {
        publishRuntimeToPlatform(snapshot);
        g_publishedRevision = revision;
    }
    if (reinitMqtt) {
        initBambuMqtt();
    }
}

bool workshopUpdateSetChannel(UpdateChannel channel) {
    if (channel != UpdateChannel::Stable && channel != UpdateChannel::Candidate) return false;
    portENTER_CRITICAL(&g_updateMux);
    if (g_taskActive) {
        portEXIT_CRITICAL(&g_updateMux);
        return false;
    }
    if (g_runtime.channel == channel) {
        portEXIT_CRITICAL(&g_updateMux);
        return true;
    }
    g_runtime.channel = channel;
    g_runtime.phase = UpdatePhase::Idle;
    g_runtime.manifestFreshness = Freshness::Unknown;
    g_runtime.progressPercent = 0;
    g_runtime.busy = false;
    clearCandidateLocked();
    copyText(g_runtime.statusMessage, sizeof(g_runtime.statusMessage), "Channel changed. Check GitHub for updates.");
    bumpRevisionLocked();
    portEXIT_CRITICAL(&g_updateMux);
    return true;
}

bool workshopUpdateRequestCheck() {
    if (!kOtaSupported) {
        setRuntimeFailure("Device-native GitHub OTA is unavailable on this target.", false);
        return false;
    }
    if (WiFi.status() != WL_CONNECTED || isAPMode()) {
        setRuntimeFailure("Connect Workshop OS to the internet before checking for updates.", false);
        return false;
    }

    portENTER_CRITICAL(&g_updateMux);
    if (g_taskActive) {
        portEXIT_CRITICAL(&g_updateMux);
        return false;
    }
    clearCandidateLocked();
    g_runtime.phase = UpdatePhase::Checking;
    g_runtime.manifestFreshness = Freshness::Unknown;
    g_runtime.progressPercent = 0;
    g_runtime.busy = true;
    copyText(g_runtime.statusMessage, sizeof(g_runtime.statusMessage), "Checking the authoritative GitHub update manifest…");
    bumpRevisionLocked();
    portEXIT_CRITICAL(&g_updateMux);

    return startOperation(PendingOperation::Check);
}

bool workshopUpdateRequestInstall() {
    if (!kOtaSupported) {
        setRuntimeFailure("Device-native GitHub OTA is unavailable on this target.", true);
        return false;
    }

    char guardReason[112] = {};
    if (!printerUpdateGuardSatisfied(guardReason, sizeof(guardReason))) {
        portENTER_CRITICAL(&g_updateMux);
        g_runtime.phase = UpdatePhase::Available;
        g_runtime.busy = false;
        copyText(g_runtime.statusMessage, sizeof(g_runtime.statusMessage), guardReason);
        bumpRevisionLocked();
        portEXIT_CRITICAL(&g_updateMux);
        return false;
    }
    if (WiFi.status() != WL_CONNECTED || isAPMode()) {
        setRuntimeFailure("Internet connection is required to download the selected OTA image.", true);
        return false;
    }

    portENTER_CRITICAL(&g_updateMux);
    const bool installable = !g_taskActive && g_candidate.valid &&
                             g_runtime.phase == UpdatePhase::Available &&
                             g_runtime.updateAvailable;
    portEXIT_CRITICAL(&g_updateMux);
    if (!installable) return false;

    // Match the existing OTA resource policy: printer MQTT is disconnected on
    // the main loop before the TLS/flash worker starts. On failure it is
    // reinitialized later by workshopUpdateServiceLoop(), also on the main loop.
    disconnectBambuMqtt();

    portENTER_CRITICAL(&g_updateMux);
    g_runtime.phase = UpdatePhase::Downloading;
    g_runtime.progressPercent = 0;
    g_runtime.busy = true;
    g_runtime.artifactIdentityVerified = false;
    copyText(g_runtime.statusMessage, sizeof(g_runtime.statusMessage), "Starting verified GitHub OTA download…");
    bumpRevisionLocked();
    portEXIT_CRITICAL(&g_updateMux);

    if (!startOperation(PendingOperation::Install)) {
        markMqttReinitPending();
        return false;
    }
    return true;
}

WorkshopUpdateRuntimeSnapshot workshopUpdateSnapshot() {
    WorkshopUpdateRuntimeSnapshot snapshot;
    portENTER_CRITICAL(&g_updateMux);
    snapshot = g_runtime;
    portEXIT_CRITICAL(&g_updateMux);
    return snapshot;
}

const char* workshopUpdateChannelName(UpdateChannel channel) {
    switch (channel) {
        case UpdateChannel::Stable: return "Stable";
        case UpdateChannel::Candidate: return "Candidate";
        case UpdateChannel::Acceptance: return "Acceptance";
        case UpdateChannel::Unknown:
        default: return "Unknown";
    }
}

const char* workshopUpdatePhaseName(UpdatePhase phase) {
    switch (phase) {
        case UpdatePhase::Idle: return "Idle";
        case UpdatePhase::Checking: return "Checking";
        case UpdatePhase::Available: return "Available";
        case UpdatePhase::Downloading: return "Downloading";
        case UpdatePhase::Verifying: return "Verifying";
        case UpdatePhase::Staged: return "Staged";
        case UpdatePhase::Installing: return "Installing";
        case UpdatePhase::RebootRequired: return "Restarting";
        case UpdatePhase::Failed: return "Failed";
        case UpdatePhase::Unknown:
        default: return "Unknown";
    }
}
