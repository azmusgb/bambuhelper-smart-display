#pragma once

#include "workshop_platform/service_contracts.hpp"

#include <cstddef>
#include <cstdint>

void workshopPlatformBegin();
void workshopPlatformPoll();
const workshop::platform::WorkshopState& workshopPlatformState();
void workshopPlatformPublishInventoryState(const workshop::platform::InventoryProjectionState& state);
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

inline const workshop::platform::InventoryProjectionState& workshopPlatformInventoryState() {
    return workshopPlatformState().inventory;
}

inline const workshop::platform::UpdateState& workshopPlatformUpdateState() {
    return workshopPlatformState().update;
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

inline bool workshopPlatformInventoryAvailable() {
    return workshopPlatformInventoryState().available;
}

inline bool workshopPlatformInventoryQuantityUsable() {
    return workshop::platform::inventoryQuantityUsable(workshopPlatformInventoryState());
}

inline bool workshopPlatformInventoryReady() {
    return workshop::platform::inventoryReadinessClean(workshopPlatformInventoryState());
}

inline bool workshopPlatformWifiOnline() {
    return workshop::platform::isConnected(workshopPlatformState().network.wifi);
}
