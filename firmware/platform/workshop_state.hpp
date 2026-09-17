#pragma once

#include <cstddef>
#include <cstdint>

namespace workshop {
namespace platform {

static const std::size_t kLocalAddressLength = 40;
static const std::size_t kProfileIdLength = 40;
static const std::size_t kVersionLabelLength = 48;
static const std::size_t kMaxPrinterSlots = 4;

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

enum class UpdateChannel : std::uint8_t {
    Unknown = 0,
    Stable,
    Candidate,
    Acceptance,
};

enum class UpdatePhase : std::uint8_t {
    Unknown = 0,
    Idle,
    Checking,
    Available,
    Downloading,
    Verifying,
    Staged,
    Installing,
    RebootRequired,
    Failed,
};

struct PrinterState {
    Connectivity connection{Connectivity::Unknown};
    PrinterActivity activity{PrinterActivity::Unknown};
    Freshness telemetryFreshness{Freshness::Unknown};
    std::uint32_t observedAtMs{0};
    std::int16_t nozzleCelsius{0};
    std::int16_t bedCelsius{0};
    std::uint8_t progressPercent{0};
    bool configured{false};
    bool commandChannelReady{false};
    bool stopGuardRequired{true};
};

// Power state is printer-scoped but represents the mapped smart-plug channel,
// not printer telemetry. Unknown relay state remains explicit; availability of
// a plug mapping alone never proves the relay is reachable or on/off.
struct PowerState {
    Freshness freshness{Freshness::Unknown};
    std::uint32_t observedAtMs{0};
    bool mapped{false};
    bool channelReady{false};
    bool stateKnown{false};
    bool on{false};
};

struct NetworkState {
    Connectivity wifi{Connectivity::Unknown};
    Connectivity localPortal{Connectivity::Unknown};
    Connectivity cloud{Connectivity::Unknown};
    Freshness freshness{Freshness::Unknown};
    std::uint32_t observedAtMs{0};
    std::int16_t rssiDbm{0};
    char localAddress[kLocalAddressLength]{};
    bool accessPointMode{false};
};

struct InventoryProjectionState {
    Freshness freshness{Freshness::Unknown};
    std::uint32_t observedAtMs{0};
    char profileId[kProfileIdLength]{};
    bool available{false};
};

struct UpdateState {
    UpdateChannel channel{UpdateChannel::Unknown};
    UpdatePhase phase{UpdatePhase::Unknown};
    Freshness manifestFreshness{Freshness::Unknown};
    char runningVersion[kVersionLabelLength]{};
    char availableVersion[kVersionLabelLength]{};
    bool otaSupported{false};
    bool recoveryFullImageSupported{false};
    bool artifactIdentityVerified{false};
    bool rollbackAvailable{false};
};

struct CapabilityState {
    bool display{true};
    bool touch{true};
    bool printerControl{true};
    bool network{true};
    bool inventory{false};
    bool power{false};
    bool update{false};
    bool audio{false};
    bool microphone{false};
    bool bluetooth{false};
    bool media{false};
};

struct HealthState {
    std::uint64_t uptimeMs{0};
    std::uint32_t freeHeapBytes{0};
    std::uint32_t largestFreeBlockBytes{0};
    std::uint32_t freePsramBytes{0};
    bool uiResponsive{true};
    bool touchResponsive{true};
    bool printerServiceResponsive{true};
    bool networkServiceResponsive{true};
    bool inventoryServiceResponsive{true};
    bool powerServiceResponsive{true};
    bool updateServiceResponsive{true};
};

struct WorkshopState {
    PrinterState printers[kMaxPrinterSlots]{};
    PowerState power[kMaxPrinterSlots]{};
    std::uint8_t activePrinterIndex{0};
    std::uint8_t configuredPrinterCount{0};
    NetworkState network{};
    InventoryProjectionState inventory{};
    UpdateState update{};
    CapabilityState capabilities{};
    HealthState health{};
    std::uint64_t revision{0};
};

inline bool isKnown(Freshness value) {
    return value != Freshness::Unknown;
}

inline bool isUsable(Freshness value) {
    return value == Freshness::Fresh;
}

inline bool isConnected(Connectivity value) {
    return value == Connectivity::Online || value == Connectivity::Degraded;
}

inline bool validPrinterSlot(std::size_t slot) {
    return slot < kMaxPrinterSlots;
}

inline bool printerActivityIsActive(PrinterActivity activity) {
    return activity == PrinterActivity::Preparing ||
           activity == PrinterActivity::Printing ||
           activity == PrinterActivity::Paused;
}

inline bool canDispatchPrinterCommand(const WorkshopState& state, std::size_t slot) {
    if (!validPrinterSlot(slot)) return false;
    const PrinterState& printer = state.printers[slot];
    return printer.configured &&
           printer.commandChannelReady &&
           isConnected(printer.connection) &&
           printer.telemetryFreshness == Freshness::Fresh;
}

inline bool canDispatchPowerCommand(const WorkshopState& state, std::size_t slot) {
    if (!validPrinterSlot(slot)) return false;
    const PowerState& power = state.power[slot];
    return power.mapped && power.channelReady && power.freshness == Freshness::Fresh;
}

inline bool shouldPreempt(EventPriority incoming, EventPriority active) {
    return static_cast<std::uint8_t>(incoming) > static_cast<std::uint8_t>(active);
}

inline bool shouldSuspendDecorativeMedia(const WorkshopState& state) {
    if (!state.health.uiResponsive ||
        !state.health.touchResponsive ||
        !state.health.printerServiceResponsive ||
        !state.health.networkServiceResponsive) return true;
    for (std::size_t slot = 0; slot < kMaxPrinterSlots; ++slot) {
        if (printerActivityIsActive(state.printers[slot].activity)) return true;
    }
    return false;
}

}  // namespace platform
}  // namespace workshop
