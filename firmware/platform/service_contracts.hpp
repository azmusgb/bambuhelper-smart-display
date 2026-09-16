#pragma once

#include "workshop_state.hpp"

#include <cstddef>
#include <cstdint>

namespace workshop {
namespace platform {

enum class PrinterCommand : std::uint8_t {
    Pause = 0,
    Resume,
    Stop,
    ChamberLightOn,
    ChamberLightOff,
};

enum class CommandResult : std::uint8_t {
    Accepted = 0,
    RejectedInvalidSlot,
    RejectedUnavailable,
    RejectedStaleState,
    RejectedInvalidState,
    RejectedGuardRequired,
    FailedTransport,
};

inline bool printerActivityAllowsCommand(PrinterActivity activity, PrinterCommand command) {
    switch (command) {
        case PrinterCommand::Pause:
            return activity == PrinterActivity::Preparing || activity == PrinterActivity::Printing;
        case PrinterCommand::Resume:
            return activity == PrinterActivity::Paused;
        case PrinterCommand::Stop:
            return activity == PrinterActivity::Preparing ||
                   activity == PrinterActivity::Printing ||
                   activity == PrinterActivity::Paused;
        case PrinterCommand::ChamberLightOn:
        case PrinterCommand::ChamberLightOff:
            return true;
        default:
            return false;
    }
}

inline CommandResult validatePrinterCommand(
    const PrinterState& state,
    PrinterCommand command,
    bool destructiveGuardSatisfied) {
    if (!state.configured || !isConnected(state.connection)) {
        return CommandResult::RejectedUnavailable;
    }
    if (state.telemetryFreshness != Freshness::Fresh) {
        return CommandResult::RejectedStaleState;
    }
    if (!state.commandChannelReady) {
        return CommandResult::RejectedUnavailable;
    }
    if (!printerActivityAllowsCommand(state.activity, command)) {
        return CommandResult::RejectedInvalidState;
    }
    if (command == PrinterCommand::Stop && state.stopGuardRequired && !destructiveGuardSatisfied) {
        return CommandResult::RejectedGuardRequired;
    }
    return CommandResult::Accepted;
}

class IStateSink {
public:
    virtual ~IStateSink() {}
    virtual void publishPrinterState(std::size_t slot, const PrinterState& state) = 0;
    virtual void publishNetworkState(const NetworkState& state) = 0;
};

class IPrinterService {
public:
    virtual ~IPrinterService() {}
    virtual void begin(IStateSink& sink) = 0;
    virtual void poll(std::uint32_t nowMs) = 0;
    virtual PrinterState snapshot(std::size_t slot) const = 0;
    virtual CommandResult dispatch(std::size_t slot, PrinterCommand command, bool destructiveGuardSatisfied) = 0;
};

class INetworkService {
public:
    virtual ~INetworkService() {}
    virtual void begin(IStateSink& sink) = 0;
    virtual void poll(std::uint32_t nowMs) = 0;
    virtual NetworkState snapshot() const = 0;
    virtual void requestReconnect() = 0;
};

class StateStore : public IStateSink {
public:
    void publishPrinterState(std::size_t slot, const PrinterState& state) override {
        if (!validPrinterSlot(slot)) return;
        state_.printers[slot] = state;
        recomputePrinterCount();
        ++state_.revision;
    }

    void publishNetworkState(const NetworkState& state) override {
        state_.network = state;
        ++state_.revision;
    }

    void publishInventoryProjectionState(const InventoryProjectionState& state) {
        state_.inventory = state;
        ++state_.revision;
    }

    void publishHealthState(const HealthState& state) {
        state_.health = state;
        ++state_.revision;
    }

    bool setActivePrinter(std::size_t slot) {
        if (!validPrinterSlot(slot) || !state_.printers[slot].configured) return false;
        state_.activePrinterIndex = static_cast<std::uint8_t>(slot);
        ++state_.revision;
        return true;
    }

    const WorkshopState& snapshot() const { return state_; }

private:
    void recomputePrinterCount() {
        std::uint8_t count = 0;
        for (std::size_t slot = 0; slot < kMaxPrinterSlots; ++slot) {
            if (state_.printers[slot].configured) ++count;
        }
        state_.configuredPrinterCount = count;

        if (!validPrinterSlot(state_.activePrinterIndex) || !state_.printers[state_.activePrinterIndex].configured) {
            for (std::size_t slot = 0; slot < kMaxPrinterSlots; ++slot) {
                if (state_.printers[slot].configured) {
                    state_.activePrinterIndex = static_cast<std::uint8_t>(slot);
                    return;
                }
            }
            state_.activePrinterIndex = 0;
        }
    }

    WorkshopState state_{};
};

}  // namespace platform
}  // namespace workshop
