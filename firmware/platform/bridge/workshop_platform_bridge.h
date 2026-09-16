#pragma once

#include "workshop_platform/workshop_state.hpp"

#include <cstddef>
#include <cstdint>

void workshopPlatformBegin();
void workshopPlatformPoll();
const workshop::platform::WorkshopState& workshopPlatformState();

// Read-only UI facade over the normalized state store. These helpers let the
// existing Workshop OS screens migrate incrementally without reaching back into
// Bambu/Wi-Fi runtime state for facts already normalized by the platform layer.
// They do not mutate printer state and do not expose inventory authority.
inline const workshop::platform::PrinterState& workshopPlatformPrinterState(std::size_t slot) {
    const workshop::platform::WorkshopState& state = workshopPlatformState();
    static const workshop::platform::PrinterState unknown{};
    return workshop::platform::validPrinterSlot(slot) ? state.printers[slot] : unknown;
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
    const workshop::platform::PrinterActivity activity = workshopPlatformPrinterState(slot).activity;
    return activity == workshop::platform::PrinterActivity::Preparing ||
           activity == workshop::platform::PrinterActivity::Printing ||
           activity == workshop::platform::PrinterActivity::Paused;
}

inline std::uint8_t workshopPlatformPrinterProgress(std::size_t slot) {
    return workshopPlatformPrinterState(slot).progressPercent;
}

inline bool workshopPlatformWifiOnline() {
    return workshop::platform::isConnected(workshopPlatformState().network.wifi);
}
