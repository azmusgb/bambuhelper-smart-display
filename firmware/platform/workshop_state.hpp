#pragma once

#include <cstdint>
#include <string>

namespace workshop::platform {

enum class Freshness : std::uint8_t {
    Unknown = 0,
    Fresh,
    Stale,
    Conflicting,
};

enum class Connectivity : std::uint8_t {
    Unknown = 0,
    Offline,
    Connecting,
    Online,
    Degraded,
};

enum class PrinterActivity : std::uint8_t {
    Unknown = 0,
    Idle,
    Preparing,
    Printing,
    Paused,
    Finished,
    Error,
};

enum class EventPriority : std::uint8_t {
    Decorative = 0,
    Background = 1,
    Normal = 2,
    High = 3,
    Critical = 4,
};

struct PrinterState {
    Connectivity connection{Connectivity::Unknown};
    PrinterActivity activity{PrinterActivity::Unknown};
    Freshness telemetryFreshness{Freshness::Unknown};
    std::uint64_t observedAtMs{0};
    std::int16_t nozzleCelsius{0};
    std::int16_t bedCelsius{0};
    std::uint8_t progressPercent{0};
    bool commandChannelReady{false};
    bool stopGuardRequired{true};
};

struct NetworkState {
    Connectivity wifi{Connectivity::Unknown};
    Freshness freshness{Freshness::Unknown};
    std::uint64_t observedAtMs{0};
    std::int16_t rssiDbm{0};
    std::string localAddress{};
    bool localPortalReachable{false};
    bool cloudReachable{false};
};

struct InventoryProjectionState {
    // Inventory truth remains owned by Filament Inventory. Workshop OS stores only
    // the state of the profile-scoped projection it has received.
    Freshness freshness{Freshness::Unknown};
    std::uint64_t observedAtMs{0};
    std::string profileId{};
    bool available{false};
};

struct HealthState {
    std::uint64_t uptimeMs{0};
    std::uint32_t freeHeapBytes{0};
    std::uint32_t largestFreeBlockBytes{0};
    std::uint32_t freePsramBytes{0};
    bool uiResponsive{true};
    bool printerServiceResponsive{true};
    bool networkServiceResponsive{true};
};

struct WorkshopState {
    PrinterState printer{};
    NetworkState network{};
    InventoryProjectionState inventory{};
    HealthState health{};
    std::uint64_t revision{0};
};

[[nodiscard]] constexpr bool isKnown(Freshness value) noexcept {
    return value != Freshness::Unknown;
}

[[nodiscard]] constexpr bool isUsable(Freshness value) noexcept {
    return value == Freshness::Fresh;
}

[[nodiscard]] constexpr bool isConnected(Connectivity value) noexcept {
    return value == Connectivity::Online || value == Connectivity::Degraded;
}

[[nodiscard]] constexpr bool canDispatchPrinterCommand(const WorkshopState& state) noexcept {
    return state.printer.commandChannelReady &&
           isConnected(state.printer.connection) &&
           state.printer.telemetryFreshness != Freshness::Conflicting;
}

[[nodiscard]] constexpr bool shouldPreempt(EventPriority incoming, EventPriority active) noexcept {
    return static_cast<std::uint8_t>(incoming) > static_cast<std::uint8_t>(active);
}

[[nodiscard]] constexpr bool shouldSuspendDecorativeMedia(const WorkshopState& state) noexcept {
    return state.printer.activity == PrinterActivity::Preparing ||
           state.printer.activity == PrinterActivity::Printing ||
           state.printer.activity == PrinterActivity::Paused ||
           !state.health.uiResponsive ||
           !state.health.printerServiceResponsive;
}

}  // namespace workshop::platform
