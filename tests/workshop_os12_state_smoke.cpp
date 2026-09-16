#include "../firmware/platform/service_contracts.hpp"

#include <cassert>
#include <cstring>

using namespace workshop::platform;

namespace {

class FakePrinterService final : public IPrinterService {
public:
    void begin(IStateSink& sink) override {
        sink_ = &sink;
        publish();
    }

    void poll(std::uint64_t nowMs) override {
        state_.observedAtMs = nowMs;
        publish();
    }

    PrinterState snapshot() const override {
        return state_;
    }

    CommandResult dispatch(PrinterCommand command, bool destructiveGuardSatisfied) override {
        if (!state_.commandChannelReady || !isConnected(state_.connection)) {
            return CommandResult::RejectedUnavailable;
        }
        if (state_.telemetryFreshness == Freshness::Stale ||
            state_.telemetryFreshness == Freshness::Unknown ||
            state_.telemetryFreshness == Freshness::Conflicting) {
            return CommandResult::RejectedStaleState;
        }
        if (command == PrinterCommand::Stop && state_.stopGuardRequired && !destructiveGuardSatisfied) {
            return CommandResult::RejectedGuardRequired;
        }
        return CommandResult::Accepted;
    }

    void setState(const PrinterState& state) {
        state_ = state;
        publish();
    }

private:
    void publish() {
        if (sink_ != nullptr) {
            sink_->publishPrinterState(state_);
        }
    }

    IStateSink* sink_{nullptr};
    PrinterState state_{};
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
    assert(store.snapshot().revision == 2);
    assert(!canDispatchPrinterCommand(store.snapshot()));

    NetworkState connectedNetwork;
    connectedNetwork.wifi = Connectivity::Online;
    connectedNetwork.freshness = Freshness::Fresh;
    std::strncpy(connectedNetwork.localAddress, "192.0.2.10", sizeof(connectedNetwork.localAddress) - 1);
    connectedNetwork.localPortalReachable = true;
    network.setState(connectedNetwork);
    assert(isConnected(store.snapshot().network.wifi));
    assert(std::strcmp(store.snapshot().network.localAddress, "192.0.2.10") == 0);

    PrinterState readyPrinter;
    readyPrinter.connection = Connectivity::Online;
    readyPrinter.activity = PrinterActivity::Idle;
    readyPrinter.telemetryFreshness = Freshness::Fresh;
    readyPrinter.commandChannelReady = true;
    printer.setState(readyPrinter);
    assert(canDispatchPrinterCommand(store.snapshot()));
    assert(printer.dispatch(PrinterCommand::Pause, false) == CommandResult::Accepted);
    assert(printer.dispatch(PrinterCommand::Stop, false) == CommandResult::RejectedGuardRequired);
    assert(printer.dispatch(PrinterCommand::Stop, true) == CommandResult::Accepted);

    readyPrinter.telemetryFreshness = Freshness::Stale;
    printer.setState(readyPrinter);
    assert(!isUsable(store.snapshot().printer.telemetryFreshness));
    assert(printer.dispatch(PrinterCommand::Pause, false) == CommandResult::RejectedStaleState);

    readyPrinter.telemetryFreshness = Freshness::Fresh;
    readyPrinter.activity = PrinterActivity::Printing;
    printer.setState(readyPrinter);
    assert(shouldSuspendDecorativeMedia(store.snapshot()));
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
