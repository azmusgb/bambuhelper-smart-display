#pragma once

#include <cstddef>
#include <cstdint>

namespace workshop::platform {

constexpr std::size_t kLocalAddressLength = 40;
constexpr std::size_t kProfileIdLength = 40;
constexpr std::size_t kMaxPrinterSlots = 4;

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
    bool configured{false};
    bool commandChannelReady{false};
    bool stopGuardRequired{true};
};

struct NetworkState {
    Connectivity wifi{Connectivity::Unknown};
    Freshness freshness{Freshness::Unknown};
    std::uint64_t observedAtMs{0};
    std::int16_t rssiDbm{0};
    char localAddress[kLocalAddressLength]{};
    bool accessPointMode{false};
    bool localPortalReachable{false};
    bool cloudReachable{false};
};

struct InventoryProjectionState {
    // Inventory truth remains owned by Filament Inventory. Workshop OS stores only
    // the state of the profile-scoped projection it has received.
    Freshness freshness{Freshness::Unknown};
    std::uint64_t observedAtMs{0};
    char profileId[kProfileIdLength]{};
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
    PrinterState printers[kMaxPrinterSlots]{};
    std::uint8_t activePrinterIndex{0};
    std::uint8_t configuredPrinterCount{0};
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

[[nodiscard]] constexpr bool validPrinterSlot(std::size_t slot) noexcept {
    return slot < kMaxPrinterSlots;
}

[[nodiscard]] constexpr bool canDispatchPrinterCommand(const WorkshopState& state, std::size_t slot) noexcept {
    if (!validPrinterSlot(slot)) {
        return false;
    }
    const PrinterState& printer = state.printers[slot];
    return printer.configured &&
           printer.commandChannelReady &&
           isConnected(printer.connection) &&
           printer.telemetryFreshness != Freshness::Conflicting;
}

[[nodiscard]] constexpr bool shouldPreempt(EventPriority incoming, EventPriority active) noexcept {
    return static_cast<std::uint8_t>(incoming) > static_cast<std::uint8_t>(active);
}

[[nodiscard]] constexpr bool shouldSuspendDecorativeMedia(const WorkshopState& state) noexcept {
    if (!state.health.uiResponsive || !state.health.printerServiceResponsive) {
        return true;
    }
    for (std::size_t slot = 0; slot < kMaxPrinterSlots; ++slot) {
        const PrinterActivity activity = state.printers[slot].activity;
        if (activity == PrinterActivity::Preparing ||
            activity == PrinterActivity::Printing ||
            activity == PrinterActivity::Paused) {
            return true;
        }
    }
    return false;
}

}  // namespace workshop::platform
