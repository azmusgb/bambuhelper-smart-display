#pragma once

#include "workshop_platform/service_contracts.hpp"

#include <cstddef>
#include <cstdint>

void workshopPlatformBegin();
void workshopPlatformPoll();
const workshop::platform::WorkshopState& workshopPlatformState();
void workshopPlatformPublishUpdateState(const workshop::platform::UpdateState& state);

workshop::platform::CommandResult workshopPlatformDispatchPrinterCommand(
    std::size_t slot,
    workshop::platform::PrinterCommand command,
    bool destructiveGuardSatisfied = false);

workshop::platform::CommandResult workshopPlatformDispatchPowerCommand(
    std::size_t slot,
    workshop::platform::PowerCommand command,
    bool guardSatisfied = false,
    bool strongGuardSatisfied = false);

// Read-only UI facade over the normalized state store. These helpers let the
// existing Workshop OS screens migrate incrementally without reaching back into
// Bambu/Wi-Fi/Tasmota runtime state for facts already normalized by the platform
// layer. They do not mutate inventory truth or infer authoritative placement.
inline const workshop::platform::PrinterState& workshopPlatformPrinterState(std::size_t slot) {
    const workshop::platform::WorkshopState& state = workshopPlatformState();
    static const workshop::platform::PrinterState unknown{};
    return workshop::platform::validPrinterSlot(slot) ? state.printers[slot] : unknown;
}

inline const workshop::platform::PowerState& workshopPlatformPowerState(std::size_t slot) {
    const workshop::platform::WorkshopState& state = workshopPlatformState();
    static const workshop::platform::PowerState unknown{};
    return workshop::platform::validPrinterSlot(slot) ? state.power[slot] : unknown;
}

inline bool workshopPlatformPrinterConfigured(std::size_t slot) {
    return workshopPlatformPrinterState(slot).configured;
}

inline bool workshopPlatformPrinterOnline(std::size_t slot) {
    return workshop::platform::isConnected(workshopPlatformPrinterState(slot).connection);
}

inline bool workshopPlatformPrinterPaused(std::size_t slot) {
    return workshopPlatformPrinterState(slot).activity == workshop::platform::PrinterActivity::Paused;
}

inline bool workshopPlatformPrinterPrinting(std::size_t slot) {
    return workshopPlatformPrinterState(slot).activity == workshop::platform::PrinterActivity::Printing;
}

inline bool workshopPlatformPrinterActive(std::size_t slot) {
    return workshop::platform::printerActivityIsActive(workshopPlatformPrinterState(slot).activity);
}

inline std::uint8_t workshopPlatformPrinterProgress(std::size_t slot) {
    return workshopPlatformPrinterState(slot).progressPercent;
}

inline bool workshopPlatformPowerMapped(std::size_t slot) {
    return workshopPlatformPowerState(slot).mapped;
}

inline bool workshopPlatformPowerReady(std::size_t slot) {
    const workshop::platform::PowerState& state = workshopPlatformPowerState(slot);
    return state.mapped && state.channelReady && state.freshness == workshop::platform::Freshness::Fresh;
}

inline bool workshopPlatformPowerStateKnown(std::size_t slot) {
    return workshopPlatformPowerState(slot).stateKnown;
}

inline bool workshopPlatformPowerOn(std::size_t slot) {
    const workshop::platform::PowerState& state = workshopPlatformPowerState(slot);
    return state.stateKnown && state.on;
}

inline bool workshopPlatformWifiOnline() {
    return workshop::platform::isConnected(workshopPlatformState().network.wifi);
}
