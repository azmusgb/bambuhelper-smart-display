#include "../firmware/platform/runtime_adapter.hpp"
#include "../firmware/platform/service_contracts.hpp"

#include <cassert>
#include <cstring>

using namespace workshop::platform;

namespace {

class FakePrinterService final : public IPrinterService {
public:
    void begin(IStateSink& sink) override {
        sink_ = &sink;
        for (std::size_t slot = 0; slot < kMaxPrinterSlots; ++slot) {
            publish(slot);
        }
    }

    void poll(std::uint64_t nowMs) override {
        for (std::size_t slot = 0; slot < kMaxPrinterSlots; ++slot) {
            states_[slot].observedAtMs = nowMs;
            publish(slot);
        }
    }

    PrinterState snapshot(std::size_t slot) const override {
        if (!validPrinterSlot(slot)) {
            return PrinterState{};
        }
        return states_[slot];
    }

    CommandResult dispatch(
        std::size_t slot,
        PrinterCommand command,
        bool destructiveGuardSatisfied) override {
        if (!validPrinterSlot(slot)) {
            return CommandResult::RejectedInvalidSlot;
        }
        const PrinterState& state = states_[slot];
        if (!state.configured || !state.commandChannelReady || !isConnected(state.connection)) {
            return CommandResult::RejectedUnavailable;
        }
        if (state.telemetryFreshness == Freshness::Stale ||
            state.telemetryFreshness == Freshness::Unknown ||
            state.telemetryFreshness == Freshness::Conflicting) {
            return CommandResult::RejectedStaleState;
        }
        if (command == PrinterCommand::Stop && state.stopGuardRequired && !destructiveGuardSatisfied) {
            return CommandResult::RejectedGuardRequired;
        }
        return CommandResult::Accepted;
    }

    void setState(std::size_t slot, const PrinterState& state) {
        if (!validPrinterSlot(slot)) {
            return;
        }
        states_[slot] = state;
        publish(slot);
    }

private:
    void publish(std::size_t slot) {
        if (sink_ != nullptr && validPrinterSlot(slot)) {
            sink_->publishPrinterState(slot, states_[slot]);
        }
    }

    IStateSink* sink_{nullptr};
    PrinterState states_[kMaxPrinterSlots]{};
};

class FakeNetworkService final : public INetworkService {
public:
    void begin(IStateSink& sink) override {
        sink_ = &sink;
        publish();
    }

    void poll(std::uint64_t nowMs) override {
        state_.observedAtMs = nowMs;
        publish();
    }

    NetworkState snapshot() const override {
        return state_;
    }

    void requestReconnect() override {
        state_.wifi = Connectivity::Connecting;
        publish();
    }

    void setState(const NetworkState& state) {
        state_ = state;
        publish();
    }

private:
    void publish() {
        if (sink_ != nullptr) {
            sink_->publishNetworkState(state_);
        }
    }

    IStateSink* sink_{nullptr};
    NetworkState state_{};
};

}  // namespace

int main() {
    StateStore store;
    FakePrinterService printer;
    FakeNetworkService network;

    printer.begin(store);
    network.begin(store);
    assert(store.snapshot().revision == kMaxPrinterSlots + 1);
    assert(store.snapshot().configuredPrinterCount == 0);
    assert(!canDispatchPrinterCommand(store.snapshot(), 0));
    assert(!canDispatchPrinterCommand(store.snapshot(), kMaxPrinterSlots));

    LegacyNetworkObservation networkObservation;
    networkObservation.connected = true;
    networkObservation.observedAtMs = 1000;
    networkObservation.rssiDbm = -55;
    networkObservation.localAddress = "192.0.2.10";
    networkObservation.localPortalReachable = true;
    NetworkState connectedNetwork = normalizeNetworkObservation(networkObservation);
    network.setState(connectedNetwork);
    assert(isConnected(store.snapshot().network.wifi));
    assert(std::strcmp(store.snapshot().network.localAddress, "192.0.2.10") == 0);

    LegacyPrinterObservation firstObservation;
    firstObservation.configured = true;
    firstObservation.connected = true;
    firstObservation.activity = PrinterActivity::Idle;
    firstObservation.lastTelemetryAtMs = 1000;
    firstObservation.nozzleCelsius = 215;
    firstObservation.bedCelsius = 55;
    firstObservation.progressPercent = 101;
    PrinterState firstPrinter = normalizePrinterObservation(firstObservation, 1500, 1000);
    assert(firstPrinter.telemetryFreshness == Freshness::Fresh);
    assert(firstPrinter.progressPercent == 100);
    printer.setState(0, firstPrinter);
    assert(store.snapshot().configuredPrinterCount == 1);
    assert(canDispatchPrinterCommand(store.snapshot(), 0));
    assert(printer.dispatch(0, PrinterCommand::Pause, false) == CommandResult::Accepted);
    assert(printer.dispatch(0, PrinterCommand::Stop, false) == CommandResult::RejectedGuardRequired);
    assert(printer.dispatch(0, PrinterCommand::Stop, true) == CommandResult::Accepted);

    LegacyPrinterObservation secondObservation = firstObservation;
    secondObservation.activity = PrinterActivity::Printing;
    PrinterState secondPrinter = normalizePrinterObservation(secondObservation, 1500, 1000);
    printer.setState(1, secondPrinter);
    assert(store.snapshot().configuredPrinterCount == 2);
    assert(store.setActivePrinter(1));
    assert(store.snapshot().activePrinterIndex == 1);
    assert(shouldSuspendDecorativeMedia(store.snapshot()));

    PrinterState stalePrinter = normalizePrinterObservation(firstObservation, 5000, 1000);
    printer.setState(0, stalePrinter);
    assert(!isUsable(store.snapshot().printers[0].telemetryFreshness));
    assert(printer.dispatch(0, PrinterCommand::Pause, false) == CommandResult::RejectedUnavailable);

    assert(freshnessFromAge(0, 5000, 1000) == Freshness::Unknown);
    assert(freshnessFromAge(5000, 4000, 1000) == Freshness::Unknown);
    assert(shouldPreempt(EventPriority::Critical, EventPriority::Decorative));
    assert(!shouldPreempt(EventPriority::Decorative, EventPriority::Critical));

    network.requestReconnect();
    assert(store.snapshot().network.wifi == Connectivity::Connecting);

    InventoryProjectionState inventory;
    inventory.available = false;
    inventory.freshness = Freshness::Unknown;
    store.publishInventoryProjectionState(inventory);
    assert(store.snapshot().inventory.freshness == Freshness::Unknown);
    assert(store.snapshot().inventory.profileId[0] == '\0');

    return 0;
}
