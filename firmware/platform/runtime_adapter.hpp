#pragma once

#include "workshop_state.hpp"

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace workshop {
namespace platform {

// Transitional input only. These observations are populated from the existing
// Bambu/Wi-Fi runtime; they are not a second authority and contain no inventory
// identity or placement semantics.
struct LegacyPrinterObservation {
    bool configured{false};
    bool connected{false};
    PrinterActivity activity{PrinterActivity::Unknown};
    std::uint32_t lastTelemetryAtMs{0};
    std::int16_t nozzleCelsius{0};
    std::int16_t bedCelsius{0};
    std::uint8_t progressPercent{0};
};

struct LegacyNetworkObservation {
    bool connected{false};
    bool connecting{false};
    bool accessPointMode{false};
    Connectivity localPortal{Connectivity::Unknown};
    Connectivity cloud{Connectivity::Unknown};
    std::uint32_t observedAtMs{0};
    std::int16_t rssiDbm{0};
    const char* localAddress{nullptr};
};

// Parsed/validated summary of the Filament Inventory device-feed v1 contract.
// The parser/transport is responsible for validating the external schema before
// constructing this observation. This adapter only normalizes the already
// validated, profile-scoped projection into Workshop OS state.
struct InventoryFeedObservation {
    const char* profileId{nullptr};
    std::uint32_t observedAtMs{0};
    std::uint16_t spoolCount{0};
    std::uint16_t loadedCount{0};
    std::uint16_t lowCount{0};
    std::uint16_t unknownQuantityCount{0};
    std::uint16_t staleQuantityCount{0};
    std::uint16_t conflictCount{0};
    std::uint16_t invalidLineageCount{0};
    InventoryReadinessState readiness{InventoryReadinessState::Undetermined};
    bool available{false};
    bool feedStale{true};
};

// Unsigned subtraction is intentional: Arduino millis() wraps at 2^32 and this
// remains correct as long as the freshness horizon is far below half the range.
inline Freshness freshnessFromAge(
    std::uint32_t observedAtMs,
    std::uint32_t nowMs,
    std::uint32_t staleAfterMs) {
    if (observedAtMs == 0 || staleAfterMs == 0) return Freshness::Unknown;
    const std::uint32_t elapsed = nowMs - observedAtMs;
    return elapsed <= staleAfterMs ? Freshness::Fresh : Freshness::Stale;
}

inline PrinterState normalizePrinterObservation(
    const LegacyPrinterObservation& observation,
    std::uint32_t nowMs,
    std::uint32_t staleAfterMs) {
    PrinterState state;
    state.configured = observation.configured;
    state.connection = observation.connected ? Connectivity::Online : Connectivity::Offline;
    state.activity = observation.activity;
    state.observedAtMs = observation.lastTelemetryAtMs;
    state.telemetryFreshness = freshnessFromAge(observation.lastTelemetryAtMs, nowMs, staleAfterMs);
    state.nozzleCelsius = observation.nozzleCelsius;
    state.bedCelsius = observation.bedCelsius;
    state.progressPercent = observation.progressPercent > 100 ? 100 : observation.progressPercent;
    state.commandChannelReady = observation.configured && observation.connected &&
                                state.telemetryFreshness == Freshness::Fresh;
    return state;
}

inline NetworkState normalizeNetworkObservation(const LegacyNetworkObservation& observation) {
    NetworkState state;
    state.observedAtMs = observation.observedAtMs;
    state.rssiDbm = observation.rssiDbm;
    state.accessPointMode = observation.accessPointMode;
    state.localPortal = observation.localPortal;
    state.cloud = observation.cloud;

    if (observation.connected) {
        state.wifi = Connectivity::Online;
        state.freshness = Freshness::Fresh;
    } else if (observation.connecting) {
        state.wifi = Connectivity::Connecting;
        state.freshness = Freshness::Unknown;
    } else {
        state.wifi = Connectivity::Offline;
        state.freshness = observation.observedAtMs == 0 ? Freshness::Unknown : Freshness::Stale;
    }

    if (observation.localAddress != nullptr) {
        std::strncpy(state.localAddress, observation.localAddress, sizeof(state.localAddress) - 1);
        state.localAddress[sizeof(state.localAddress) - 1] = '\0';
    }
    return state;
}

inline InventoryProjectionState normalizeInventoryFeedObservation(
    const InventoryFeedObservation& observation) {
    InventoryProjectionState state;
    state.available = observation.available;
    state.observedAtMs = observation.observedAtMs;
    state.spoolCount = observation.spoolCount;
    state.loadedCount = observation.loadedCount;
    state.lowCount = observation.lowCount;
    state.unknownQuantityCount = observation.unknownQuantityCount;
    state.staleQuantityCount = observation.staleQuantityCount;
    state.conflictCount = observation.conflictCount;
    state.invalidLineageCount = observation.invalidLineageCount;
    state.readiness = observation.readiness;

    if (observation.profileId != nullptr) {
        std::strncpy(state.profileId, observation.profileId, sizeof(state.profileId) - 1);
        state.profileId[sizeof(state.profileId) - 1] = '\0';
    }

    if (!observation.available) {
        state.freshness = Freshness::Unknown;
        state.quantityState = InventoryQuantityState::Unknown;
        state.verificationRequired = true;
        return state;
    }

    state.freshness = observation.feedStale ? Freshness::Stale : Freshness::Fresh;

    if (observation.invalidLineageCount > 0) {
        state.quantityState = InventoryQuantityState::InvalidLineage;
    } else if (observation.conflictCount > 0) {
        state.quantityState = InventoryQuantityState::Conflict;
        state.freshness = Freshness::Conflicting;
    } else if (observation.staleQuantityCount > 0 || observation.feedStale) {
        state.quantityState = InventoryQuantityState::Stale;
    } else if (observation.unknownQuantityCount > 0) {
        state.quantityState = InventoryQuantityState::Unknown;
    } else {
        state.quantityState = InventoryQuantityState::Current;
    }

    state.verificationRequired =
        state.quantityState != InventoryQuantityState::Current ||
        state.freshness != Freshness::Fresh ||
        state.readiness == InventoryReadinessState::Undetermined ||
        state.readiness == InventoryReadinessState::EvidenceStale;

    return state;
}

}  // namespace platform
}  // namespace workshop
