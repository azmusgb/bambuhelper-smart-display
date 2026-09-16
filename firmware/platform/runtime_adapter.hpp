#pragma once

#include "workshop_state.hpp"

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace workshop::platform {

// Transitional input only. These observations are populated from the existing
// Bambu/Wi-Fi runtime; they are not a second authority and contain no inventory
// identity or placement semantics.
struct LegacyPrinterObservation {
    bool configured{false};
    bool connected{false};
    PrinterActivity activity{PrinterActivity::Unknown};
    std::uint64_t lastTelemetryAtMs{0};
    std::int16_t nozzleCelsius{0};
    std::int16_t bedCelsius{0};
    std::uint8_t progressPercent{0};
};

struct LegacyNetworkObservation {
    bool connected{false};
    bool connecting{false};
    bool accessPointMode{false};
    bool localPortalReachable{false};
    bool cloudReachable{false};
    std::uint64_t observedAtMs{0};
    std::int16_t rssiDbm{0};
    const char* localAddress{nullptr};
};

[[nodiscard]] constexpr Freshness freshnessFromAge(
    std::uint64_t observedAtMs,
    std::uint64_t nowMs,
    std::uint64_t staleAfterMs) noexcept {
    if (observedAtMs == 0 || staleAfterMs == 0) {
        return Freshness::Unknown;
    }
    if (nowMs < observedAtMs) {
        // millis()/clock rollover or invalid ordering: never manufacture Fresh.
        return Freshness::Unknown;
    }
    return (nowMs - observedAtMs) <= staleAfterMs ? Freshness::Fresh : Freshness::Stale;
}

[[nodiscard]] inline PrinterState normalizePrinterObservation(
    const LegacyPrinterObservation& observation,
    std::uint64_t nowMs,
    std::uint64_t staleAfterMs) noexcept {
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

[[nodiscard]] inline NetworkState normalizeNetworkObservation(
    const LegacyNetworkObservation& observation) noexcept {
    NetworkState state;
    state.observedAtMs = observation.observedAtMs;
    state.rssiDbm = observation.rssiDbm;
    state.accessPointMode = observation.accessPointMode;
    state.localPortalReachable = observation.localPortalReachable;
    state.cloudReachable = observation.cloudReachable;

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

}  // namespace workshop::platform
