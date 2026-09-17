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

enum class PowerCommand : std::uint8_t {
    On = 0,
    Off,
};

enum class CommandResult : std::uint8_t {
    Accepted = 0,
    RejectedInvalidSlot,
    RejectedUnavailable,
    RejectedStaleState,
    RejectedCommandChannelUnavailable,
    RejectedInvalidState,
    RejectedGuardRequired,
    RejectedStrongGuardRequired,
    FailedTransport,
};

// Canonical operation feedback states for touch/browser presentation. The UI
// may enter Pending before dispatch, then derive the terminal presentation from
// the authoritative command result. FatalError is reserved for failures that
// require explicit intervention/recovery; ordinary command rejection and
// transport failure remain recoverable and must never be presented as success.
enum class OperationPhase : std::uint8_t {
    Idle = 0,
    Pending,
    Success,
    RecoverableError,
    FatalError,
};

struct CommandOperationState {
    OperationPhase phase{OperationPhase::Idle};
    CommandResult result{CommandResult::Accepted};
    bool retryable{false};
};

inline CommandOperationState pendingCommandOperation() {
    CommandOperationState state;
    state.phase = OperationPhase::Pending;
    state.retryable = false;
    return state;
}

inline CommandOperationState commandOperationFromResult(CommandResult result) {
    CommandOperationState state;
    state.result = result;
    if (result == CommandResult::Accepted) {
        state.phase = OperationPhase::Success;
        state.retryable = false;
        return state;
    }

    state.phase = OperationPhase::RecoverableError;
    switch (result) {
        case CommandResult::RejectedUnavailable:
        case CommandResult::RejectedStaleState:
        case CommandResult::RejectedCommandChannelUnavailable:
        case CommandResult::FailedTransport:
            state.retryable = true;
            break;
        default:
            state.retryable = false;
            break;
    }
    return state;
}

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
        return CommandResult::RejectedCommandChannelUnavailable;
    }
    if (!printerActivityAllowsCommand(state.activity, command)) {
        return CommandResult::RejectedInvalidState;
    }
    if (command == PrinterCommand::Stop && state.stopGuardRequired && !destructiveGuardSatisfied) {
        return CommandResult::RejectedGuardRequired;
    }
    return CommandResult::Accepted;
}

// Power On is permitted when the mapped plug itself is fresh/reachable even if
// the printer is currently offline; turning the plug on is often what makes the
// printer reachable. Power Off is always guarded. An active print or anything
// other than fresh printer telemetry requires the stronger explicit guard.
inline CommandResult validatePowerCommand(
    const PowerState& power,
    const PrinterState& printer,
    PowerCommand command,
    bool guardSatisfied,
    bool strongGuardSatisfied) {
    if (!power.mapped) {
        return CommandResult::RejectedUnavailable;
    }
    if (!power.channelReady) {
        return CommandResult::RejectedCommandChannelUnavailable;
    }
    if (power.freshness != Freshness::Fresh) {
        return CommandResult::RejectedStaleState;
    }
    if (command == PowerCommand::On) {
        return CommandResult::Accepted;
    }
    if (!guardSatisfied) {
        return CommandResult::RejectedGuardRequired;
    }

    const bool uncertainPrinterState =
        printer.telemetryFreshness != Freshness::Fresh ||
        printer.activity == PrinterActivity::Unknown;
    const bool activePrinter = printerActivityIsActive(printer.activity);
    if ((uncertainPrinterState || activePrinter) && !strongGuardSatisfied) {
        return CommandResult::RejectedStrongGuardRequired;
    }
    return CommandResult::Accepted;
}

class IStateSink {
public:
    virtual ~IStateSink() {}
    virtual void publishPrinterState(std::size_t slot, const PrinterState& state) = 0;
    virtual void publishPowerState(std::size_t slot, const PowerState& state) = 0;
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

class IPowerService {
public:
    virtual ~IPowerService() {}
    virtual void begin(IStateSink& sink) = 0;
    virtual void poll(std::uint32_t nowMs) = 0;
    virtual PowerState snapshot(std::size_t slot) const = 0;
    virtual CommandResult dispatch(
        std::size_t slot,
        PowerCommand command,
        const PrinterState& printer,
        bool guardSatisfied,
        bool strongGuardSatisfied) = 0;
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

    void publishPowerState(std::size_t slot, const PowerState& state) override {
        if (!validPrinterSlot(slot)) return;
        state_.power[slot] = state;
        recomputeCapabilities();
        ++state_.revision;
    }

    void publishNetworkState(const NetworkState& state) override {
        state_.network = state;
        ++state_.revision;
    }

    void publishInventoryProjectionState(const InventoryProjectionState& state) {
        state_.inventory = state;
        state_.capabilities.inventory = state.available;
        ++state_.revision;
    }

    void publishUpdateState(const UpdateState& state) {
        state_.update = state;
        state_.capabilities.update = state.otaSupported;
        ++state_.revision;
    }

    void publishHealthState(const HealthState& state) {
        state_.health = state;
        ++state_.revision;
    }

    void publishCapabilityState(const CapabilityState& state) {
        state_.capabilities = state;
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
    void recomputeCapabilities() {
        bool power = false;
        for (std::size_t slot = 0; slot < kMaxPrinterSlots; ++slot) {
            if (state_.power[slot].mapped) {
                power = true;
                break;
            }
        }
        state_.capabilities.power = power;
    }

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
