#pragma once

#include "workshop_state.hpp"

#include <cstdint>

namespace workshop::platform {

enum class PrinterCommand : std::uint8_t {
    Pause = 0,
    Resume,
    Stop,
    ChamberLightOn,
    ChamberLightOff,
};

enum class CommandResult : std::uint8_t {
    Accepted = 0,
    RejectedUnavailable,
    RejectedStaleState,
    RejectedGuardRequired,
    FailedTransport,
};

class IStateSink {
public:
    virtual ~IStateSink() = default;
    virtual void publishPrinterState(const PrinterState& state) = 0;
    virtual void publishNetworkState(const NetworkState& state) = 0;
};

class IPrinterService {
public:
    virtual ~IPrinterService() = default;

    virtual void begin(IStateSink& sink) = 0;
    virtual void poll(std::uint64_t nowMs) = 0;
    virtual PrinterState snapshot() const = 0;

    // Destructive actions remain guarded by the caller/UI contract. The service
    // must never silently downgrade a guarded Stop into an unguarded action.
    virtual CommandResult dispatch(PrinterCommand command, bool destructiveGuardSatisfied) = 0;
};

class INetworkService {
public:
    virtual ~INetworkService() = default;

    virtual void begin(IStateSink& sink) = 0;
    virtual void poll(std::uint64_t nowMs) = 0;
    virtual NetworkState snapshot() const = 0;
    virtual void requestReconnect() = 0;
};

// Central ownership point for normalized runtime state. Services publish facts;
// views consume snapshots. Views do not reach around the store to mutate service
// state or invent authoritative inventory facts.
class StateStore final : public IStateSink {
public:
    void publishPrinterState(const PrinterState& state) override {
        state_.printer = state;
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

    [[nodiscard]] const WorkshopState& snapshot() const noexcept {
        return state_;
    }

private:
    WorkshopState state_{};
};

}  // namespace workshop::platform
