#include "workshop_inventory_service.h"

#include "wifi_manager.h"
#include "workshop_platform_bridge.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>

#include <cstdint>
#include <cstring>

namespace {
using workshop::platform::Freshness;
using workshop::platform::InventoryFeedObservation;
using workshop::platform::InventoryReadinessState;
using workshop::platform::InventoryProjectionState;

constexpr char kFeedUrl[] = "https://filamentinventory.netlify.app/api/device-feed/v1";
constexpr char kPreferencesNamespace[] = "ws12-fi";
constexpr char kCredentialKey[] = "device_token";
constexpr char kTokenPrefix[] = "fi_dev_";
constexpr std::size_t kTokenLength = 50;  // prefix + 43 base64url characters
constexpr std::uint32_t kRefreshIntervalMs = 5UL * 60UL * 1000UL;
constexpr std::uint32_t kRetryIntervalMs = 60UL * 1000UL;
constexpr std::uint32_t kMaxPayloadBytes = 96UL * 1024UL;

#if defined(BOARD_IS_WS350) && defined(ENABLE_OTA_AUTO)
constexpr bool kHttpsSupported = true;
extern const std::uint8_t rootca_crt_bundle_start[] asm("_binary_x509_crt_bundle_start");
#else
constexpr bool kHttpsSupported = false;
#endif

portMUX_TYPE g_inventoryMux = portMUX_INITIALIZER_UNLOCKED;
WorkshopInventoryRuntimeSnapshot g_runtime;
char g_deviceToken[kTokenLength + 1] = {};
bool g_refreshRequested = false;
bool g_taskActive = false;

void copyText(char* dst, std::size_t len, const char* src) {
    if (!dst || len == 0) return;
    if (!src) src = "";
    strlcpy(dst, src, len);
}

bool validDeviceToken(const char* token) {
    if (!token || std::strlen(token) != kTokenLength) return false;
    if (std::strncmp(token, kTokenPrefix, sizeof(kTokenPrefix) - 1) != 0) return false;
    for (std::size_t i = sizeof(kTokenPrefix) - 1; i < kTokenLength; ++i) {
        const char c = token[i];
        const bool allowed =
            (c >= 'A' && c <= 'Z') ||
            (c >= 'a' && c <= 'z') ||
            (c >= '0' && c <= '9') ||
            c == '_' || c == '-';
        if (!allowed) return false;
    }
    return true;
}

InventoryReadinessState readinessFromText(const char* value) {
    if (!value) return InventoryReadinessState::Undetermined;
    if (std::strcmp(value, "Ready") == 0) return InventoryReadinessState::Ready;
    if (std::strcmp(value, "ReadyWithSubstitute") == 0) return InventoryReadinessState::ReadyWithSubstitute;
    if (std::strcmp(value, "NeedsLoad") == 0) return InventoryReadinessState::NeedsLoad;
    if (std::strcmp(value, "NeedsDry") == 0) return InventoryReadinessState::NeedsDry;
    if (std::strcmp(value, "InsufficientQuantity") == 0) return InventoryReadinessState::InsufficientQuantity;
    if (std::strcmp(value, "EvidenceStale") == 0) return InventoryReadinessState::EvidenceStale;
    return InventoryReadinessState::Undetermined;
}

void publishUnavailable(const char* message, bool credentialConfigured, std::uint32_t nowMs) {
    InventoryProjectionState state;
    state.available = false;
    state.freshness = Freshness::Unknown;
    state.quantityVerificationRequired = true;
    state.placementVerificationRequired = true;
    workshopPlatformPublishInventoryState(state);

    portENTER_CRITICAL(&g_inventoryMux);
    g_runtime.state = state;
    g_runtime.credentialConfigured = credentialConfigured;
    g_runtime.busy = false;
    g_runtime.lastAttemptAtMs = nowMs;
    copyText(g_runtime.statusMessage, sizeof(g_runtime.statusMessage), message);
    portEXIT_CRITICAL(&g_inventoryMux);
}

bool parseFeed(JsonDocument& doc, InventoryFeedObservation& observation, char* error, std::size_t errorLen) {
    if ((doc["schemaVersion"] | 0) != 1) {
        copyText(error, errorLen, "Unsupported Filament Inventory device-feed schema.");
        return false;
    }

    JsonObject scope = doc["scope"].as<JsonObject>();
    if (scope.isNull() || std::strcmp(scope["type"] | "", "profile") != 0) {
        copyText(error, errorLen, "Device feed is not profile scoped.");
        return false;
    }
    const char* profileId = scope["id"] | "";
    if (!profileId[0] || std::strlen(profileId) >= workshop::platform::kProfileIdLength) {
        copyText(error, errorLen, "Device feed profile identity is missing or too long.");
        return false;
    }

    JsonObject freshness = doc["freshness"].as<JsonObject>();
    JsonObject inventory = doc["inventory"].as<JsonObject>();
    JsonArray spools = inventory["spools"].as<JsonArray>();
    JsonObject readiness = doc["readiness"].as<JsonObject>();
    if (freshness.isNull() || inventory.isNull() || spools.isNull() || readiness.isNull()) {
        copyText(error, errorLen, "Device feed is missing required sections.");
        return false;
    }
    if (std::strcmp(inventory["status"] | "", "available") != 0) {
        copyText(error, errorLen, "Authoritative Filament Inventory state is unavailable.");
        return false;
    }

    observation = InventoryFeedObservation{};
    observation.profileId = profileId;
    observation.available = true;
    observation.feedStale = freshness["stale"] | true;
    observation.readiness = readinessFromText(readiness["state"] | "Undetermined");

    std::uint16_t spoolCount = 0;
    std::uint16_t loadedCount = 0;
    std::uint16_t lowCount = 0;
    std::uint16_t unknownQuantityCount = 0;
    std::uint16_t staleQuantityCount = 0;
    std::uint16_t quantityConflictCount = 0;
    std::uint16_t invalidLineageCount = 0;
    std::uint16_t unknownPlacementCount = 0;
    std::uint16_t stalePlacementCount = 0;
    std::uint16_t placementConflictCount = 0;

    for (JsonObject spool : spools) {
        const char* spoolId = spool["spoolId"] | "";
        if (!spoolId[0]) {
            copyText(error, errorLen, "Device feed contains a spool without canonical spoolId.");
            return false;
        }
        ++spoolCount;

        const char* stockState = spool["stockState"] | "Unknown";
        JsonObject quantity = spool["quantity"].as<JsonObject>();
        JsonObject placement = spool["placement"].as<JsonObject>();
        if (quantity.isNull() || placement.isNull()) {
            copyText(error, errorLen, "Device feed spool is missing evidence sections.");
            return false;
        }

        const char* quantityStatus = quantity["status"] | "Unknown";
        const bool quantityVerify = quantity["verificationRequired"] | true;
        if (std::strcmp(quantityStatus, "Current") == 0) {
            if (quantityVerify || quantity["remainingGrams"].isNull()) {
                copyText(error, errorLen, "Current quantity evidence failed verification contract.");
                return false;
            }
            if (std::strcmp(stockState, "Low") == 0) ++lowCount;
            else if (std::strcmp(stockState, "Unknown") == 0) {
                copyText(error, errorLen, "Current quantity evidence cannot expose Unknown stock state.");
                return false;
            }
        } else if (std::strcmp(quantityStatus, "Stale") == 0) {
            ++staleQuantityCount;
        } else if (std::strcmp(quantityStatus, "Conflict") == 0) {
            ++quantityConflictCount;
        } else if (std::strcmp(quantityStatus, "InvalidLineage") == 0) {
            ++invalidLineageCount;
        } else if (std::strcmp(quantityStatus, "Unknown") == 0) {
            ++unknownQuantityCount;
        } else {
            copyText(error, errorLen, "Device feed contains an unknown quantity evidence state.");
            return false;
        }

        const char* placementStatus = placement["status"] | "Unknown";
        const char* placementState = placement["state"] | "Unknown";
        const bool placementVerify = placement["verificationRequired"] | true;
        if (std::strcmp(placementStatus, "Current") == 0) {
            if (placementVerify) {
                copyText(error, errorLen, "Current placement evidence unexpectedly requires verification.");
                return false;
            }
            if (std::strcmp(placementState, "Loaded") == 0) ++loadedCount;
        } else if (std::strcmp(placementStatus, "Stale") == 0) {
            ++stalePlacementCount;
        } else if (std::strcmp(placementStatus, "Conflict") == 0) {
            ++placementConflictCount;
        } else if (std::strcmp(placementStatus, "Unknown") == 0) {
            ++unknownPlacementCount;
        } else {
            copyText(error, errorLen, "Device feed contains an unknown placement evidence state.");
            return false;
        }
    }

    observation.spoolCount = spoolCount;
    observation.loadedCount = loadedCount;
    observation.lowCount = lowCount;
    observation.unknownQuantityCount = unknownQuantityCount;
    observation.staleQuantityCount = staleQuantityCount;
    observation.conflictCount = quantityConflictCount;
    observation.invalidLineageCount = invalidLineageCount;
    observation.unknownPlacementCount = unknownPlacementCount;
    observation.stalePlacementCount = stalePlacementCount;
    observation.placementConflictCount = placementConflictCount;
    return true;
}

#if defined(BOARD_IS_WS350) && defined(ENABLE_OTA_AUTO)
bool fetchFeed(InventoryFeedObservation& observation, char* error, std::size_t errorLen) {
    if (WiFi.status() != WL_CONNECTED || isAPMode()) {
        copyText(error, errorLen, "Connect Workshop OS to Wi-Fi before refreshing Filament Inventory.");
        return false;
    }

    char token[kTokenLength + 1] = {};
    portENTER_CRITICAL(&g_inventoryMux);
    std::memcpy(token, g_deviceToken, sizeof(token));
    portEXIT_CRITICAL(&g_inventoryMux);
    if (!validDeviceToken(token)) {
        copyText(error, errorLen, "A valid Workshop OS device token has not been configured.");
        return false;
    }

    WiFiClientSecure client;
    client.setCACertBundle(rootca_crt_bundle_start);
    HTTPClient http;
    http.setTimeout(15000);
    http.setConnectTimeout(10000);
    http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);
    http.setUserAgent("WorkshopOS-WS350/12");
    if (!http.begin(client, kFeedUrl)) {
        copyText(error, errorLen, "Could not initialize the Filament Inventory request.");
        return false;
    }

    http.addHeader("Accept", "application/json");
    String authorization = "Bearer ";
    authorization += token;
    http.addHeader("Authorization", authorization);
    std::memset(token, 0, sizeof(token));

    const int code = http.GET();
    if (code != HTTP_CODE_OK) {
        if (code == HTTP_CODE_UNAUTHORIZED) {
            copyText(error, errorLen, "Workshop OS device access was rejected or revoked.");
        } else {
            snprintf(error, errorLen, "Filament Inventory request failed (HTTP %d).", code);
        }
        http.end();
        return false;
    }

    const int size = http.getSize();
    if (size <= 0 || static_cast<std::uint32_t>(size) > kMaxPayloadBytes) {
        copyText(error, errorLen, "Filament Inventory response size is missing or outside the accepted limit.");
        http.end();
        return false;
    }

    JsonDocument doc;
    const DeserializationError jsonError = deserializeJson(doc, http.getStream());
    http.end();
    if (jsonError) {
        copyText(error, errorLen, "Filament Inventory returned invalid JSON.");
        return false;
    }

    return parseFeed(doc, observation, error, errorLen);
}
#endif

void refreshTask(void*) {
    InventoryFeedObservation observation;
    char error[112] = {};
    const std::uint32_t nowMs = millis();
    bool ok = false;

#if defined(BOARD_IS_WS350) && defined(ENABLE_OTA_AUTO)
    ok = fetchFeed(observation, error, sizeof(error));
#else
    copyText(error, sizeof(error), "Filament Inventory HTTPS feed is unavailable on this target.");
#endif

    if (ok) {
        observation.observedAtMs = nowMs;
        InventoryProjectionState normalized =
            workshop::platform::normalizeInventoryFeedObservation(observation);
        workshopPlatformPublishInventoryState(normalized);

        portENTER_CRITICAL(&g_inventoryMux);
        g_runtime.state = normalized;
        g_runtime.busy = false;
        g_runtime.lastAttemptAtMs = nowMs;
        g_runtime.lastSuccessAtMs = nowMs;
        g_runtime.credentialConfigured = true;
        copyText(g_runtime.statusMessage, sizeof(g_runtime.statusMessage), "Filament Inventory device feed is current.");
        g_taskActive = false;
        portEXIT_CRITICAL(&g_inventoryMux);
    } else {
        const bool configured = workshopInventoryCredentialConfigured();
        publishUnavailable(error[0] ? error : "Filament Inventory refresh failed.", configured, nowMs);
        portENTER_CRITICAL(&g_inventoryMux);
        g_taskActive = false;
        portEXIT_CRITICAL(&g_inventoryMux);
    }

    vTaskDelete(nullptr);
}

bool startRefresh() {
    portENTER_CRITICAL(&g_inventoryMux);
    if (g_taskActive) {
        portEXIT_CRITICAL(&g_inventoryMux);
        return false;
    }
    g_taskActive = true;
    g_refreshRequested = false;
    g_runtime.busy = true;
    g_runtime.lastAttemptAtMs = millis();
    copyText(g_runtime.statusMessage, sizeof(g_runtime.statusMessage), "Refreshing Filament Inventory…");
    portEXIT_CRITICAL(&g_inventoryMux);

    const BaseType_t created = xTaskCreatePinnedToCore(
        refreshTask,
        "ws12Inventory",
        12288,
        nullptr,
        3,
        nullptr,
        1);
    if (created != pdPASS) {
        portENTER_CRITICAL(&g_inventoryMux);
        g_taskActive = false;
        g_runtime.busy = false;
        copyText(g_runtime.statusMessage, sizeof(g_runtime.statusMessage), "Could not start the inventory refresh worker.");
        portEXIT_CRITICAL(&g_inventoryMux);
        return false;
    }
    return true;
}

}  // namespace

void workshopInventoryServiceBegin() {
    Preferences prefs;
    char token[kTokenLength + 1] = {};
    if (prefs.begin(kPreferencesNamespace, true)) {
        const String stored = prefs.getString(kCredentialKey, "");
        prefs.end();
        if (validDeviceToken(stored.c_str())) strlcpy(token, stored.c_str(), sizeof(token));
    }

    portENTER_CRITICAL(&g_inventoryMux);
    g_runtime = WorkshopInventoryRuntimeSnapshot{};
    std::memcpy(g_deviceToken, token, sizeof(g_deviceToken));
    g_runtime.credentialConfigured = validDeviceToken(g_deviceToken);
    copyText(
        g_runtime.statusMessage,
        sizeof(g_runtime.statusMessage),
        g_runtime.credentialConfigured
            ? "Filament Inventory access configured; waiting for refresh."
            : "Create a read-only WS350 token in Filament Inventory and add it in Local Portal.");
    g_refreshRequested = g_runtime.credentialConfigured;
    g_taskActive = false;
    portEXIT_CRITICAL(&g_inventoryMux);
    std::memset(token, 0, sizeof(token));

    publishUnavailable(
        g_runtime.credentialConfigured ? "Waiting for Filament Inventory refresh." :
                                         "Filament Inventory device access is not configured.",
        g_runtime.credentialConfigured,
        millis());
}

void workshopInventoryServiceLoop() {
    WorkshopInventoryRuntimeSnapshot snap;
    bool requested = false;
    portENTER_CRITICAL(&g_inventoryMux);
    snap = g_runtime;
    requested = g_refreshRequested;
    portEXIT_CRITICAL(&g_inventoryMux);

    if (!snap.credentialConfigured || snap.busy) return;
    const std::uint32_t nowMs = millis();
    const std::uint32_t interval = snap.lastSuccessAtMs ? kRefreshIntervalMs : kRetryIntervalMs;
    const bool due = snap.lastAttemptAtMs == 0 || static_cast<std::uint32_t>(nowMs - snap.lastAttemptAtMs) >= interval;
    if (requested || due) startRefresh();
}

bool workshopInventoryRequestRefresh() {
    portENTER_CRITICAL(&g_inventoryMux);
    if (!g_runtime.credentialConfigured) {
        portEXIT_CRITICAL(&g_inventoryMux);
        return false;
    }
    g_refreshRequested = true;
    const bool idle = !g_taskActive;
    portEXIT_CRITICAL(&g_inventoryMux);
    return idle;
}

bool workshopInventorySetDeviceCredential(const char* token) {
    if (!validDeviceToken(token)) return false;

    Preferences prefs;
    if (!prefs.begin(kPreferencesNamespace, false)) return false;
    const std::size_t written = prefs.putString(kCredentialKey, token);
    prefs.end();
    if (written != kTokenLength) return false;

    portENTER_CRITICAL(&g_inventoryMux);
    strlcpy(g_deviceToken, token, sizeof(g_deviceToken));
    g_runtime.credentialConfigured = true;
    g_refreshRequested = true;
    copyText(g_runtime.statusMessage, sizeof(g_runtime.statusMessage), "Workshop OS device access saved. Refresh pending.");
    portEXIT_CRITICAL(&g_inventoryMux);
    return true;
}

void workshopInventoryClearDeviceCredential() {
    Preferences prefs;
    if (prefs.begin(kPreferencesNamespace, false)) {
        prefs.remove(kCredentialKey);
        prefs.end();
    }

    portENTER_CRITICAL(&g_inventoryMux);
    std::memset(g_deviceToken, 0, sizeof(g_deviceToken));
    g_runtime.credentialConfigured = false;
    g_refreshRequested = false;
    portEXIT_CRITICAL(&g_inventoryMux);

    publishUnavailable("Filament Inventory device access removed.", false, millis());
}

bool workshopInventoryCredentialConfigured() {
    portENTER_CRITICAL(&g_inventoryMux);
    const bool configured = validDeviceToken(g_deviceToken);
    portEXIT_CRITICAL(&g_inventoryMux);
    return configured;
}

WorkshopInventoryRuntimeSnapshot workshopInventorySnapshot() {
    WorkshopInventoryRuntimeSnapshot snap;
    portENTER_CRITICAL(&g_inventoryMux);
    snap = g_runtime;
    portEXIT_CRITICAL(&g_inventoryMux);
    return snap;
}
